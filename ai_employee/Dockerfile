FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Core deps first (cached layer)
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] python-dotenv anthropic pydantic \
    requests tweepy python-multipart websockets \
    pyyaml python-frontmatter apscheduler tenacity \
    watchdog Pillow pandas rich typer \
    google-auth google-auth-oauthlib google-api-python-client \
    aiohttp httpx requests-oauthlib

# Optional: RAG (skip if too large for free tier)
RUN pip install --no-cache-dir chromadb 2>/dev/null || true

COPY . .

RUN mkdir -p vault/Needs_Action vault/Pending_Approval vault/Approved \
             vault/Rejected vault/Done vault/Logs vault/Scheduled \
             vault/Cancelled vault/Failed vault/Bank_Uploads \
             vault/Briefings vault/pids sessions/whatsapp credentials

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DRY_RUN=true
ENV VAULT_PATH=/app/vault
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "python -m uvicorn api.server:app --host 0.0.0.0 --port ${PORT}"]
