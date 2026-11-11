# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Layer A — heavy ML packages (torch + sentence-transformers, ~2 GB).
# Installed before COPY requirements.txt so this layer is only invalidated
# when the pinned version changes, not on every code or dep change.
RUN pip install --no-cache-dir --prefix=/install "sentence-transformers==3.4.1"

# Layer B — remaining application dependencies (fast, no torch).
COPY requirements.txt .
RUN grep -v "sentence-transformers" requirements.txt | \
    pip install --no-cache-dir --prefix=/install -r /dev/stdin

# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /install /usr/local
COPY . .

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
