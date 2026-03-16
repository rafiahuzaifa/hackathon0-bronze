"""
memory/rag_memory.py — RAG AI Memory
Gold Tier — Panaversity AI Employee Hackathon 2026

Indexes all vault markdown files into ChromaDB for semantic search.
Falls back to keyword search if ChromaDB is unavailable.

Usage:
    from memory.rag_memory import RAGMemory
    rag = RAGMemory(vault_path=Path("./vault"))
    rag.index_vault()
    results = rag.search("partnership email from TechCorp", n=5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("memory.rag")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Return (metadata_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: Dict[str, Any] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    return meta, parts[2].strip()


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> List[str]:
    """Split text into overlapping chunks for better retrieval."""
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks or [text]


def _file_id(path: Path) -> str:
    return hashlib.md5(str(path).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# RAGMemory
# ---------------------------------------------------------------------------

class RAGMemory:
    """
    Semantic search over the entire vault using ChromaDB + sentence-transformers.
    Falls back to BM25-style keyword search if dependencies unavailable.
    """

    def __init__(self, vault_path: Optional[Path] = None, persist_dir: Optional[Path] = None):
        self.vault_path = vault_path or Path(os.environ.get("VAULT_PATH", "./vault"))
        self.persist_dir = persist_dir or (self.vault_path.parent / "chroma_db")
        self._collection = None
        self._fallback_docs: List[Dict[str, Any]] = []
        self._use_chroma = False
        self._init_chroma()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_dir))

            # Use sentence-transformers if available, else chromadb default
            try:
                ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            except Exception:
                ef = embedding_functions.DefaultEmbeddingFunction()

            self._collection = client.get_or_create_collection(
                name="vault_docs",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._use_chroma = True
            logger.info("ChromaDB initialised at %s", self.persist_dir)
        except ImportError:
            logger.warning("chromadb not installed — using keyword fallback search")
        except Exception as exc:
            logger.warning("ChromaDB init failed (%s) — using keyword fallback", exc)

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_vault(self, force: bool = False) -> int:
        """
        Walk vault directory and index all .md files.
        Returns number of documents indexed.
        """
        if not self.vault_path.exists():
            logger.warning("Vault path does not exist: %s", self.vault_path)
            return 0

        indexed = 0
        for md_file in self.vault_path.rglob("*.md"):
            try:
                indexed += self._index_file(md_file, force=force)
            except Exception as exc:
                logger.debug("Skip %s: %s", md_file.name, exc)

        logger.info("RAG index: %d documents", indexed)
        return indexed

    def _index_file(self, path: Path, force: bool = False) -> int:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return 0

        meta, body = _parse_frontmatter(text)
        # Build rich document text
        doc_text = f"{path.stem}\n{meta.get('subject', meta.get('title', ''))}\n{body}"

        doc_meta = {
            "filename": path.name,
            "path": str(path.relative_to(self.vault_path.parent)),
            "type": str(meta.get("type", meta.get("source", _guess_type(path)))),
            "date": str(meta.get("created_at", datetime.fromtimestamp(path.stat().st_mtime).isoformat())),
            "risk": str(meta.get("risk", "")),
            "status": str(meta.get("status", _guess_status(path))),
        }

        if self._use_chroma and self._collection is not None:
            chunks = _chunk_text(doc_text)
            ids, texts, metas = [], [], []
            for i, chunk in enumerate(chunks):
                cid = f"{_file_id(path)}_{i}"
                ids.append(cid)
                texts.append(chunk)
                metas.append({**doc_meta, "chunk_index": str(i), "total_chunks": str(len(chunks))})
            try:
                if force:
                    try:
                        self._collection.delete(ids=ids)
                    except Exception:
                        pass
                self._collection.upsert(ids=ids, documents=texts, metadatas=metas)
            except Exception as exc:
                logger.debug("Chroma upsert failed for %s: %s", path.name, exc)
        else:
            # Fallback: store in memory
            self._fallback_docs.append({
                "id": _file_id(path),
                "text": doc_text.lower(),
                "raw": doc_text[:500],
                "meta": doc_meta,
            })

        return 1

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, n: int = 8, type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Semantic search over vault documents.
        Returns list of {title, type, preview, date, path, relevance} dicts.
        """
        if not query.strip():
            return []

        if self._use_chroma and self._collection is not None:
            return self._chroma_search(query, n, type_filter)
        return self._keyword_search(query, n, type_filter)

    def _chroma_search(self, query: str, n: int, type_filter: Optional[str]) -> List[Dict[str, Any]]:
        where = {"type": type_filter} if type_filter else None
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n * 2, 20),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("Chroma query failed: %s", exc)
            return self._keyword_search(query, n, type_filter)

        out: List[Dict[str, Any]] = []
        seen_files: set = set()

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            fname = meta.get("filename", "")
            if fname in seen_files:
                continue
            seen_files.add(fname)
            relevance = max(0, round((1 - dist) * 100))
            out.append({
                "id": _file_id(Path(meta.get("path", fname))),
                "title": _title_from_filename(fname),
                "type": meta.get("type", "vault"),
                "preview": doc[:200],
                "date": meta.get("date", "")[:10],
                "path": meta.get("path", fname),
                "relevance": relevance,
                "risk": meta.get("risk", ""),
                "status": meta.get("status", ""),
            })
            if len(out) >= n:
                break

        return sorted(out, key=lambda x: x["relevance"], reverse=True)

    def _keyword_search(self, query: str, n: int, type_filter: Optional[str]) -> List[Dict[str, Any]]:
        """BM25-style keyword search fallback."""
        terms = query.lower().split()
        scored = []
        for doc in self._fallback_docs:
            if type_filter and doc["meta"].get("type") != type_filter:
                continue
            score = sum(doc["text"].count(t) for t in terms)
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, doc in scored[:n]:
            meta = doc["meta"]
            out.append({
                "id": doc["id"],
                "title": _title_from_filename(meta.get("filename", "")),
                "type": meta.get("type", "vault"),
                "preview": doc["raw"][:200],
                "date": meta.get("date", "")[:10],
                "path": meta.get("path", ""),
                "relevance": min(99, score * 15),
                "risk": meta.get("risk", ""),
                "status": meta.get("status", ""),
            })
        return out

    # ── Delete / Stats ────────────────────────────────────────────────────────

    def delete_file(self, path: Path) -> None:
        fid = _file_id(path)
        if self._use_chroma and self._collection is not None:
            try:
                existing = self._collection.get(where={"filename": path.name})
                if existing["ids"]:
                    self._collection.delete(ids=existing["ids"])
            except Exception:
                pass
        else:
            self._fallback_docs = [d for d in self._fallback_docs if d["id"] != fid]

    def stats(self) -> Dict[str, Any]:
        if self._use_chroma and self._collection is not None:
            count = self._collection.count()
        else:
            count = len(self._fallback_docs)
        return {
            "backend": "chromadb" if self._use_chroma else "keyword_fallback",
            "total_chunks": count,
            "persist_dir": str(self.persist_dir),
            "vault_path": str(self.vault_path),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _guess_type(path: Path) -> str:
    name = path.name.upper()
    if name.startswith("EMAIL"): return "email"
    if name.startswith("WHATSAPP") or name.startswith("WA_"): return "whatsapp"
    if name.startswith("LINKEDIN"): return "social"
    if name.startswith("TWITTER"): return "social"
    if name.startswith("FACEBOOK") or name.startswith("INSTAGRAM"): return "social"
    if name.startswith("SOCIAL"): return "social"
    if name.startswith("BANK"): return "bank"
    if "BRIEFING" in name or "REPORT" in name: return "report"
    return "vault"


def _guess_status(path: Path) -> str:
    parts = path.parts
    for part in parts:
        p = part.lower()
        if "done" in p: return "done"
        if "needs_action" in p: return "needs_action"
        if "pending" in p: return "pending_approval"
        if "approved" in p: return "approved"
        if "failed" in p: return "failed"
    return "unknown"


def _title_from_filename(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"_(\d{8,})", "", name)
    return name.replace("_", " ").title()


# ── Singleton accessor ────────────────────────────────────────────────────────

_rag_instance: Optional[RAGMemory] = None


def get_rag(vault_path: Optional[Path] = None) -> RAGMemory:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGMemory(vault_path=vault_path)
        _rag_instance.index_vault()
    return _rag_instance
