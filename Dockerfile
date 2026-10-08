# SRMA Agent - Clinical Evidence Synthesis Portal
#
# Single container: FastAPI backend + prebuilt React UI (ui/dist).
# The clinical model (MedGemma) is called remotely on Vertex AI, so no GPU
# or model weights are needed here. Gemini orchestration uses AI Studio.
#
# Build locally:   docker build -t srma-agent .
# Run locally:     docker run -p 8080:8080 --env-file .env srma-agent
# Cloud Run:       scripts/deploy_cloud_run.sh

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # matplotlib needs a writable cache dir; the image filesystem is read-only
    # friendly on Cloud Run except /tmp.
    MPLCONFIGDIR=/tmp/mpl \
    # Run artefacts go here; on Cloud Run this path is a mounted GCS bucket.
    SRMA_RUNS_DIR=/data/runs \
    # No local Ollama inside the container: fail cleanly instead of trying.
    SRMA_VERTEX_FALLBACK_TO_LOCAL=0 \
    PORT=8080

WORKDIR /app

# System deps: fonts for matplotlib/reportlab rendering, certs for HTTPS.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Python deps first so the layer is cached across code changes.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application code + compiled UI. node_modules/.venv/runs are excluded by
# .dockerignore.
COPY srma_agent ./srma_agent
COPY ui/dist ./ui/dist
COPY scripts ./scripts

RUN mkdir -p /data/runs /tmp/mpl

EXPOSE 8080

# Cloud Run injects $PORT. One worker: review jobs are in-process background
# threads and their state lives in memory, so all requests must hit the same
# process (the deploy script also pins max-instances=1).
CMD ["sh", "-c", "uvicorn srma_agent.web_server:app --host 0.0.0.0 --port ${PORT} --workers 1"]
