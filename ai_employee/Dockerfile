# ─────────────────────────────────────────────
# AI Employee — Python Backend
# FastAPI + Orchestrator + Watchers
# ─────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps for Playwright (WhatsApp watcher)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─────────────────────────────────────────────
# Install Python dependencies
# ─────────────────────────────────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium (for WhatsApp watcher)
RUN playwright install chromium --with-deps || true

# ─────────────────────────────────────────────
# Copy application code
# ─────────────────────────────────────────────
COPY . .

# Create vault directories
RUN mkdir -p vault/Needs_Action \
             vault/Pending_Approval \
             vault/Approved \
             vault/Rejected \
             vault/Done \
             vault/Logs \
             vault/pids \
             vault/sessions \
             uploads/bank

# Non-root user
RUN addgroup --system --gid 1001 aiemployee \
 && adduser  --system --uid 1001 --ingroup aiemployee aiemployee \
 && chown -R aiemployee:aiemployee /app

USER aiemployee

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
