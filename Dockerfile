# syntax=docker/dockerfile:1

# ── Stage: runtime ───────────────────────────────────────────────────────────
# Use python:3.12-slim to match the project's tested Python version.
# The slim variant omits dev headers and docs, keeping the image lean while
# still providing full pip / C-extension support for packages like grpcio.
FROM python:3.12-slim

# Cloud Run best-practices: don't run as root.
RUN groupadd --system appuser && useradd --system --gid appuser appuser

# Set the working directory early so all subsequent paths are relative.
WORKDIR /app

# ── Install dependencies ─────────────────────────────────────────────────────
# Copy only requirements.txt first to exploit Docker layer caching:
# if source code changes but requirements don't, this layer is reused.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ────────────────────────────────────────────────────
# .dockerignore excludes .git, .venv, __pycache__, .env, tests/, etc.
COPY --chown=appuser:appuser . .

# Switch to non-root user for runtime.
USER appuser

# ── Entrypoint ───────────────────────────────────────────────────────────────
# Cloud Run injects the PORT environment variable at container start time.
# The container MUST listen on $PORT — hardcoding any port causes a health-
# check failure and deployment rollback.  Using shell form (/bin/sh -c) so
# the shell expands $PORT before passing it to Streamlit.
#
# --server.headless=true   suppresses the browser-open prompt in a headless env
# --server.address=0.0.0.0 binds to all interfaces (required for Cloud Run)
# --server.enableCORS=false Cloud Run handles TLS/CORS at the load balancer
CMD ["/bin/sh", "-c", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false"]
