#!/usr/bin/env bash
# Deploy the SRMA Agent portal to Cloud Run.
#
# What this sets up (idempotent - safe to re-run):
#   1. A GCS bucket for run artefacts, mounted into the container at
#      /data/runs via Cloud Run volume mounts, so results survive restarts.
#   2. Secret Manager secrets for GOOGLE_API_KEY (Gemini) - read from .env
#      the first time, never printed, never baked into the image.
#   3. A dedicated service account with the minimum roles:
#        roles/aiplatform.user           - call the MedGemma Vertex endpoint
#        roles/secretmanager.secretAccessor
#        roles/storage.objectAdmin       - on the runs bucket only
#   4. The Cloud Run service, built from source with Cloud Build.
#
# Why these Cloud Run settings:
#   --min-instances 1 --max-instances 1   review jobs run as background
#        threads with in-memory state; every request must reach the same,
#        always-alive instance. One instance is plenty for a client pilot.
#   --no-cpu-throttling                   keep CPU on between requests so a
#        60-minute review keeps running while the browser merely polls.
#   --timeout 3600                        the longest a single HTTP request
#        may take (the UI polls, so this is just a ceiling).
#
# Usage:
#   scripts/deploy_cloud_run.sh                 # deploy / update
#   SERVICE=srma-agent-staging scripts/deploy_cloud_run.sh
#
# Prereqs: gcloud authenticated; Owner/Editor on the project; .env present
# with GOOGLE_API_KEY (only needed the first time, to create the secret).

set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT_ID="${PROJECT_ID:-apps-project-13102025}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-srma-agent-staging}"
BUCKET="${BUCKET:-${PROJECT_ID}-srma-runs}"
SA_NAME="${SA_NAME:-srma-agent-run}"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_GEMINI="${SECRET_GEMINI:-srma-google-api-key}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

# Vertex MedGemma endpoint - read from .env so there is one source of truth.
envval() { grep -E "^$1=" .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r' || true; }
VERTEX_LOCATION="$(envval SRMA_VERTEX_LOCATION)";             VERTEX_LOCATION="${VERTEX_LOCATION:-asia-southeast1}"
VERTEX_ENDPOINT_ID="$(envval SRMA_VERTEX_MEDGEMMA_ENDPOINT_ID)"
VERTEX_PROJECT_NUMBER="$(envval SRMA_VERTEX_PROJECT_NUMBER)";  VERTEX_PROJECT_NUMBER="${VERTEX_PROJECT_NUMBER:-${PROJECT_NUMBER}}"
if [[ -z "${VERTEX_ENDPOINT_ID}" ]]; then
  echo "ERROR: SRMA_VERTEX_MEDGEMMA_ENDPOINT_ID not found in .env" >&2; exit 1
fi

echo "==> Project ${PROJECT_ID} (${PROJECT_NUMBER}), region ${REGION}, service ${SERVICE}"
gcloud config set project "${PROJECT_ID}" >/dev/null

# ---------------------------------------------------------------- 1. bucket
if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
  echo "==> Creating bucket gs://${BUCKET}"
  gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" \
      --uniform-bucket-level-access --public-access-prevention
else
  echo "==> Bucket gs://${BUCKET} exists"
fi

# --------------------------------------------------------------- 2. secrets
ensure_secret() {  # name, env-var-name
  local name="$1" var="$2" val
  if gcloud secrets describe "${name}" >/dev/null 2>&1; then
    echo "==> Secret ${name} exists (not modified)"
    return
  fi
  val="$(envval "${var}")"
  if [[ -z "${val}" ]]; then
    echo "ERROR: ${var} is empty in .env and secret ${name} does not exist yet." >&2
    exit 1
  fi
  echo "==> Creating secret ${name} from .env ${var}"
  printf '%s' "${val}" | gcloud secrets create "${name}" --data-file=- --replication-policy=automatic
}
ensure_secret "${SECRET_GEMINI}" GOOGLE_API_KEY

# ------------------------------------------------------- 3. service account
# Default: the project's compute service account, which every other Cloud Run
# service in this project already uses and which already holds the Vertex /
# Secret Manager / Storage permissions. Granting roles to a *new* account
# needs project-level setIamPolicy (Owner); Editors cannot do that.
#
# For a least-privilege identity, have an Owner run once:
#   gcloud projects add-iam-policy-binding PROJECT \
#     --member=serviceAccount:srma-agent-run@PROJECT.iam.gserviceaccount.com \
#     --role=roles/aiplatform.user
# then deploy with:  DEDICATED_SA=1 scripts/deploy_cloud_run.sh
if [[ "${DEDICATED_SA:-0}" == "1" ]]; then
  if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
    echo "==> Creating service account ${SA_EMAIL}"
    gcloud iam service-accounts create "${SA_NAME}" --display-name="SRMA Agent Cloud Run"
  fi
  echo "==> Granting roles to ${SA_EMAIL}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" --role="roles/aiplatform.user" --condition=None >/dev/null \
    || echo "WARN: could not grant roles/aiplatform.user at project level (needs Owner). Ask an Owner to run the command in the comment above."
else
  SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  echo "==> Using default compute service account ${SA_EMAIL} (set DEDICATED_SA=1 for least-privilege)"
fi
# The compute SA already has project-wide access; these explicit grants only
# matter for the dedicated SA. Setting IAM on a secret/bucket needs
# setIamPolicy on that resource, which Editors may lack - so warn, don't fail.
gcloud secrets add-iam-policy-binding "${SECRET_GEMINI}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 \
  || echo "WARN: could not bind secretAccessor on ${SECRET_GEMINI} (ok if ${SA_EMAIL} already has project-level access)"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin" >/dev/null 2>&1 \
  || echo "WARN: could not bind objectAdmin on gs://${BUCKET} (ok if ${SA_EMAIL} already has project-level access)"

# ------------------------------------------------------------ 4. deploy
echo "==> Deploying ${SERVICE} from source (Cloud Build)"
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SA_EMAIL}" \
  --cpu 2 --memory 4Gi \
  --min-instances 1 --max-instances 1 \
  --concurrency 40 \
  --timeout 3600 \
  --no-cpu-throttling \
  --execution-environment gen2 \
  --add-volume "name=runs,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=runs,mount-path=/data/runs" \
  --set-secrets "GOOGLE_API_KEY=${SECRET_GEMINI}:latest" \
  --set-env-vars "^@^SRMA_RUNS_DIR=/data/runs@SRMA_CLINICAL_MODEL=vertex_medgemma@SRMA_VERTEX_FALLBACK_TO_LOCAL=0@SRMA_VERTEX_PROJECT_ID=${PROJECT_ID}@SRMA_VERTEX_PROJECT_NUMBER=${VERTEX_PROJECT_NUMBER}@SRMA_VERTEX_LOCATION=${VERTEX_LOCATION}@SRMA_VERTEX_MEDGEMMA_ENDPOINT_ID=${VERTEX_ENDPOINT_ID}@SRMA_VERTEX_TIMEOUT=180@SRMA_CLINICAL_MAX_WORKERS=8@SRMA_MAX_ABSTRACTS_TO_SCREEN=0@SRMA_MAX_STUDIES_TO_EXTRACT=0@SRMA_MAX_RECORDS_PER_SOURCE=200@GOOGLE_GENAI_USE_VERTEXAI=FALSE"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"
echo
echo "==> Deployed: ${URL}"
echo "    health : ${URL}/api/status"
echo "    runs   : gs://${BUCKET}"
echo
echo "Smoke test:"
curl -fsS "${URL}/api/status" | python3 -m json.tool || echo "(status endpoint not ready yet - retry in a minute)"
