"""Central configuration for the SRMA Agent.

Two models are used, deliberately (see ADK_MEDGEMMA_IMPLEMENTATION_PLAN.md):

  ORCHESTRATOR  - decides which tool to call, assembles reports.
                  Needs reliable function-calling, so a Gemini model served
                  by Google AI Studio (the Gemini Developer API).
  CLINICAL      - reads supplied text and makes clinical judgements.
                  MedGemma 4B, run locally via Ollama. Never calls tools.

WHY THE SPLIT IS NOT OPTIONAL
AI Studio serves Google's own hosted models only. MedGemma 4B cannot be
uploaded to it, so the clinical model has to run somewhere we control
(Ollama locally, or a Vertex endpoint later). Conversely a 4B model is not
reliable enough at multi-step function calling to drive the pipeline. Each
model is used for the job it is actually good at.

Everything is overridable by environment variable so the same code runs
locally (free) and in production.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.getenv("SRMA_RUNS_DIR", PROJECT_ROOT / "runs"))
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """Load .env without requiring python-dotenv."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
# LiteLLM model strings.
#   ollama_chat/<name>  - uses Ollama's /api/chat endpoint (better formatting
#                         than the older ollama/ prefix, which uses /api/generate)
#   vertex_medgemma     - the MedGemma model deployed on a Vertex AI
#                         dedicated prediction endpoint (see below). This is
#                         the production path; Ollama is the local fallback.
CLINICAL_MODEL = os.getenv("SRMA_CLINICAL_MODEL", "vertex_medgemma")

# Local MedGemma via Ollama. Kept as the automatic fallback: if the Vertex
# endpoint is unreachable or returns an error, llm.py transparently retries
# the same call against this model so a review never dies mid-screening.
LOCAL_CLINICAL_MODEL = os.getenv("SRMA_LOCAL_CLINICAL_MODEL", "ollama_chat/medgemma")

# --------------------------------------------------------------------------
# MedGemma on Vertex AI (dedicated endpoint, chatCompletions request format)
# --------------------------------------------------------------------------
# The endpoint is a *dedicated* Vertex endpoint, which has its own DNS name
# of the form <endpoint-id>.<region>-<project-number>.prediction.vertexai.goog
# rather than the shared <region>-aiplatform.googleapis.com host. The full
# URL is therefore assembled from these parts. Everything is overridable so
# the same code works against a different deployment without edits.
VERTEX_PROJECT_ID = os.getenv("SRMA_VERTEX_PROJECT_ID", "332110629135").strip()
VERTEX_PROJECT_NUMBER = os.getenv("SRMA_VERTEX_PROJECT_NUMBER", "781612439219").strip()
VERTEX_LOCATION = os.getenv("SRMA_VERTEX_LOCATION", "asia-southeast1").strip()
VERTEX_MEDGEMMA_ENDPOINT_ID = os.getenv(
    "SRMA_VERTEX_MEDGEMMA_ENDPOINT_ID",
    "mg-endpoint-b81452c7-c8ea-4102-8139-5b3a53d09106",
).strip()

# Explicit override wins; otherwise build the dedicated-endpoint URL.
VERTEX_MEDGEMMA_PREDICT_URL = os.getenv("SRMA_VERTEX_MEDGEMMA_URL", "").strip() or (
    f"https://{VERTEX_MEDGEMMA_ENDPOINT_ID}.{VERTEX_LOCATION}-{VERTEX_PROJECT_NUMBER}"
    f".prediction.vertexai.goog/v1/projects/{VERTEX_PROJECT_ID}"
    f"/locations/{VERTEX_LOCATION}/endpoints/{VERTEX_MEDGEMMA_ENDPOINT_ID}:predict"
)

# Dedicated endpoints running vLLM can take a while on a long extraction
# prompt; be generous rather than discard a correct answer as a timeout.
VERTEX_TIMEOUT = int(os.getenv("SRMA_VERTEX_TIMEOUT", "180"))

# When the Vertex call fails (auth, quota, 5xx, network) fall back to the
# local Ollama model instead of aborting. Set to 0 to make failures fatal.
VERTEX_FALLBACK_TO_LOCAL = os.getenv("SRMA_VERTEX_FALLBACK_TO_LOCAL", "1").strip() in ("1", "true", "TRUE")

# Bare Gemini model ids are resolved by ADK against whichever backend
# GOOGLE_GENAI_USE_VERTEXAI selects. Flash is chosen over Pro because the
# orchestrator only routes tool calls and assembles text that other
# components already computed; it does no clinical reasoning.
#
# Model ids are retired on Google's schedule, not ours: gemini-2.0-flash
# began returning 404 with "no longer available, please update your code".
# There is no pinning that prevents this, so when it happens again, override
# it without touching code by adding to .env:
#     SRMA_ORCHESTRATOR_MODEL=<whatever the error message names>
# List what your key can currently see with:
#     ./.venv/bin/python scripts/run_review.py --list-models
ORCHESTRATOR_MODEL = os.getenv("SRMA_ORCHESTRATOR_MODEL", "gemini-3.6-flash")

# Ollama binds IPv4 127.0.0.1 by default. Do not use "localhost" here: on
# some hosts it resolves only to IPv6 ::1, which Ollama is not listening on,
# producing a confusing "connection refused". The NO_PROXY block below stops
# proxies from rejecting the literal IP as "direct IP access".
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")
os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)

# Ollama is local. If an HTTP(S)_PROXY is set (common on corporate machines
# and in sandboxes), requests to localhost would otherwise be routed through
# it and rejected. Exclude loopback explicitly.
_NO_PROXY_HOSTS = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
for _var in ("NO_PROXY", "no_proxy"):
    _existing = [h for h in os.environ.get(_var, "").split(",") if h.strip()]
    for _host in _NO_PROXY_HOSTS:
        if _host not in _existing:
            _existing.append(_host)
    os.environ[_var] = ",".join(_existing)



# --------------------------------------------------------------------------
# Gemini backend: Google AI Studio
# --------------------------------------------------------------------------
# ADK and google-genai choose their backend from GOOGLE_GENAI_USE_VERTEXAI.
# We pin it to FALSE so the Gemini Developer API (AI Studio) is used and a
# plain API key is sufficient. Left unset, google-genai may attempt Vertex
# and fail on missing Application Default Credentials, which produces a
# confusing auth error rather than an obvious "no API key" one.
#
# Get a key at https://aistudio.google.com/apikey and put it in .env as:
#     GOOGLE_API_KEY=...
GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY")
                  or os.getenv("GEMINI_API_KEY", "")).strip()
if GOOGLE_API_KEY:
    # ADK reads GOOGLE_API_KEY; mirror GEMINI_API_KEY into it if only that
    # was supplied, so either spelling works in .env.
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

USE_VERTEX = os.environ["GOOGLE_GENAI_USE_VERTEXAI"].upper() in ("1", "TRUE")
HAS_GEMINI = bool(GOOGLE_API_KEY) or USE_VERTEX
GEMINI_BACKEND = "vertex-ai" if USE_VERTEX else "ai-studio"


def google_api_key_hint() -> str:
    """Describe how GOOGLE_API_KEY differs from a typical AI Studio key.

    This is a *hint*, never a verdict. It is only worth showing after a real
    API call has already failed, to help explain why.

    The distinction matters because key formats are not ours to police:
    consumer AI Studio issues 39-character keys beginning "AIza", but
    Workspace and internal Google accounts issue other shapes that work
    perfectly well. Treating the common case as the only valid case would
    tell users their working key is broken - so the live call decides, and
    this only ever adds colour to a failure.

    Returns "" when nothing looks unusual.
    """
    if USE_VERTEX or not GOOGLE_API_KEY:
        return ""
    if GOOGLE_API_KEY.startswith(("AQ.", "ya29.")):
        return ("This key has the shape of a Google OAuth access token. Those "
                "usually expire after about an hour, so if it worked earlier "
                "today it may simply have aged out - try issuing a fresh one.")
    if not GOOGLE_API_KEY.startswith("AIza"):
        return ("Consumer AI Studio keys start with 'AIza' and are 39 "
                "characters; this one does not match that pattern. That is "
                "normal for some account types, so it may not be the problem.")
    if len(GOOGLE_API_KEY) != 39:
        return (f"This key is {len(GOOGLE_API_KEY)} characters where 39 is "
                "typical, which can mean it was truncated when pasted.")
    return ""

# Without a key the orchestrator falls back to the local model. Slower and
# weaker at tool calling, but it keeps the agent runnable offline instead of
# failing at import time.
if not HAS_GEMINI:
    ORCHESTRATOR_MODEL = os.getenv("SRMA_ORCHESTRATOR_MODEL", CLINICAL_MODEL)


# --------------------------------------------------------------------------
# Data source credentials (all optional - every source works without them)
# --------------------------------------------------------------------------
# Raises PubMed rate limit 3/sec -> 10/sec. https://ncbi.nlm.nih.gov/account/
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()

# Required by NCBI etiquette and by OpenAlex/Unpaywall "polite pools",
# which give faster, more reliable service to identified callers.
CONTACT_EMAIL = os.getenv("SRMA_CONTACT_EMAIL", "srma-agent@example.org").strip()

# Optional; lifts Semantic Scholar out of the shared rate-limit pool.
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()

USER_AGENT = f"SRMA-Agent/1.0 (mailto:{CONTACT_EMAIL})"


# --------------------------------------------------------------------------
# Search behaviour
# --------------------------------------------------------------------------
# Per-source cap on records retrieved. Systematic reviews want recall.
MAX_RECORDS_PER_SOURCE = int(os.getenv("SRMA_MAX_RECORDS_PER_SOURCE", "200"))

# Processing caps. These existed only because a 4B model on a laptop CPU
# takes ~10-40s per abstract. With MedGemma served from a Vertex endpoint
# the bottleneck is gone, so the defaults are now UNBOUNDED (0 = no cap):
# every deduplicated record is screened and every included study is
# extracted, which is what PRISMA actually requires. Set a positive number
# in .env to reintroduce a ceiling for a quick smoke test.
MAX_ABSTRACTS_TO_SCREEN = int(os.getenv("SRMA_MAX_ABSTRACTS_TO_SCREEN", "0"))
MAX_STUDIES_TO_EXTRACT = int(os.getenv("SRMA_MAX_STUDIES_TO_EXTRACT", "0"))

# Concurrent records in flight during screening / extraction. A hosted
# endpoint scales horizontally; a local CPU model does not, so the number is
# chosen from the clinical backend unless overridden.
_DEFAULT_WORKERS = "8" if CLINICAL_MODEL.startswith("vertex") else "2"
CLINICAL_MAX_WORKERS = int(os.getenv("SRMA_CLINICAL_MAX_WORKERS", _DEFAULT_WORKERS))

HTTP_TIMEOUT = int(os.getenv("SRMA_HTTP_TIMEOUT", "30"))
HTTP_MAX_RETRIES = int(os.getenv("SRMA_HTTP_MAX_RETRIES", "3"))


def _api_key_status() -> str:
    if not GOOGLE_API_KEY:
        return "NOT SET (falling back to local model)"
    return f"set ({len(GOOGLE_API_KEY)} chars)"


def _cap(value: int) -> str:
    return "unbounded" if not value or value <= 0 else str(value)


def summary() -> str:
    """Human-readable config dump, printed at pipeline start for reproducibility."""
    return "\n".join([
        "SRMA Agent configuration",
        f"  gemini backend     : {GEMINI_BACKEND}",
        f"  orchestrator model : {ORCHESTRATOR_MODEL}",
        f"  clinical model     : {CLINICAL_MODEL}",
        f"  vertex endpoint    : {VERTEX_MEDGEMMA_ENDPOINT_ID} ({VERTEX_LOCATION})",
        f"  local fallback     : {LOCAL_CLINICAL_MODEL} ({'enabled' if VERTEX_FALLBACK_TO_LOCAL else 'disabled'})",
        f"  ollama base        : {OLLAMA_API_BASE}",
        f"  clinical workers   : {CLINICAL_MAX_WORKERS}",
        f"  google api key     : {_api_key_status()}",
        f"  ncbi api key       : {'set' if NCBI_API_KEY else 'not set (3 req/sec limit)'}",
        f"  contact email      : {CONTACT_EMAIL}",
        f"  max per source     : {MAX_RECORDS_PER_SOURCE}",
        f"  max to screen      : {_cap(MAX_ABSTRACTS_TO_SCREEN)}",
        f"  max to extract     : {_cap(MAX_STUDIES_TO_EXTRACT)}",
        f"  runs dir           : {RUNS_DIR}",
    ])

