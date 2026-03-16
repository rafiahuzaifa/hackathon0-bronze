#!/usr/bin/env bash
# ============================================================
# AI Employee — Full Startup Script
# Gold Tier — Panaversity AI Employee Hackathon 2026
# ============================================================
# Usage:
#   ./start.sh          → install deps + launch everything
#   ./start.sh api      → API server only
#   ./start.sh setup    → run OAuth setup wizard

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_DIR="$ROOT/ai_employee"
DASHBOARD_DIR="$ROOT/nextjs-dashboard"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[AI-Employee]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
cat << 'EOF'
  ___    ___   ___                     _
 / _ \  |_ _| | __|  _ __   _ __ | | ___  _   _  ___  ___
| (_) |  | |  | _|  | '  \ | '_ \| |/ _ \| | | |/ _ \/ _ \
 \__\_\ |___| |___|  |_|_|_|| .__/|_|\___/ \__, |\___/\___/
                              |_|           |___/
 Personal AI Employee — Gold Tier — Panaversity Hackathon 2026
EOF
echo -e "${NC}"

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  err "Python 3 not found. Install Python 3.10+ first."
  exit 1
fi
PYTHON=$(command -v python3)
log "Python: $($PYTHON --version)"

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f "$AI_DIR/.env" ]; then
  if [ -f "$AI_DIR/.env.example" ]; then
    warn ".env not found — copying from .env.example"
    cp "$AI_DIR/.env.example" "$AI_DIR/.env"
    warn "Edit $AI_DIR/.env and add your API keys, then re-run."
  else
    err ".env not found. Create $AI_DIR/.env with your credentials."
    exit 1
  fi
fi

# ── Install Python deps ───────────────────────────────────────────────────────
log "Installing Python dependencies..."
$PYTHON -m pip install -q --upgrade pip
$PYTHON -m pip install -q -r "$AI_DIR/requirements.txt"
log "Dependencies installed ✓"

# ── Install Playwright Chromium ───────────────────────────────────────────────
log "Installing Playwright Chromium (for WhatsApp)..."
$PYTHON -m playwright install chromium --with-deps 2>/dev/null \
  || $PYTHON -m playwright install chromium \
  || warn "Playwright install failed — WhatsApp automation won't work"
log "Playwright ready ✓"

# ── Create vault directories ──────────────────────────────────────────────────
log "Creating vault directories..."
mkdir -p "$AI_DIR/vault/"{Needs_Action,Pending_Approval,Approved,Rejected,Done,Logs,Scheduled,Cancelled,Failed,Bank_Uploads,Briefings}
mkdir -p "$AI_DIR/sessions/whatsapp"
mkdir -p "$AI_DIR/credentials"
mkdir -p "$AI_DIR/pids"
log "Vault ready ✓"

# ── Sub-command handling ──────────────────────────────────────────────────────
CMD="${1:-all}"

if [ "$CMD" = "setup" ]; then
  log "Starting OAuth setup wizard..."
  cd "$AI_DIR"
  $PYTHON -m setup.oauth_setup
  exit 0
fi

if [ "$CMD" = "api" ]; then
  log "Starting API server only on http://0.0.0.0:8000 ..."
  cd "$AI_DIR"
  $PYTHON -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
  exit 0
fi

if [ "$CMD" = "dashboard" ]; then
  log "Starting Next.js dashboard on http://localhost:3000 ..."
  cd "$DASHBOARD_DIR"
  npm install --silent
  npm run dev
  exit 0
fi

# ── Launch everything (default) ───────────────────────────────────────────────
log "Starting ALL services..."

# 1. API Server (background)
log "→ Starting FastAPI server on :8000"
cd "$AI_DIR"
$PYTHON -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
API_PID=$!
echo $API_PID > "$AI_DIR/pids/api_server.pid"
log "  API server PID: $API_PID"
sleep 2

# 2. Vault RAG index (background, non-blocking)
log "→ Indexing vault for RAG search..."
$PYTHON -c "
import sys; sys.path.insert(0,'.')
from memory.rag_memory import get_rag
from pathlib import Path
rag = get_rag(vault_path=Path('vault'))
n = rag.index_vault()
print(f'  RAG: {n} documents indexed')
" &

# 3. Watchdog monitor (background)
log "→ Starting watchdog monitor"
$PYTHON watchdog_monitor.py &
WATCHDOG_PID=$!
echo $WATCHDOG_PID > "$AI_DIR/pids/watchdog.pid"

# 4. Gmail watcher (background, if configured)
if grep -q "GMAIL_TOKEN_PATH" "$AI_DIR/.env" 2>/dev/null; then
  log "→ Starting Gmail watcher"
  $PYTHON -c "
import sys; sys.path.insert(0,'.')
from watchers.gmail_watcher import GmailWatcher
import time, os
from pathlib import Path
w = GmailWatcher(vault_path=Path(os.environ.get('VAULT_PATH','./vault')))
w.start()
" &
  echo $! > "$AI_DIR/pids/gmail.pid"
fi

# 5. Next.js dashboard (foreground)
log "→ Starting Next.js dashboard on :3000"
cd "$DASHBOARD_DIR"
if [ ! -d "node_modules" ]; then
  log "  Installing npm dependencies..."
  npm install --silent
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      AI Employee is running!                         ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Dashboard:  http://localhost:3000                   ║${NC}"
echo -e "${GREEN}║  API:        http://localhost:8000                   ║${NC}"
echo -e "${GREEN}║  API Docs:   http://localhost:8000/docs              ║${NC}"
echo -e "${GREEN}║  Setup:      http://localhost:3000/setup             ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${YELLOW}║  Go to /setup to enter your API credentials          ║${NC}"
echo -e "${YELLOW}║  Then click Go LIVE in the header to enable actions  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

# ── Cleanup on exit ───────────────────────────────────────────────────────────
trap "echo 'Shutting down...'; kill $API_PID $WATCHDOG_PID 2>/dev/null; exit 0" SIGINT SIGTERM
