#!/usr/bin/env bash
set -euo pipefail

# Going to repo root.
cd "$(dirname "$0")/../.."
REPO_ROOT="$(pwd)"

hr() { echo "────────────────────────────────────────────────────────"; }

IMAGE_NAME="anybuddy-ingestion"
DOCKERFILE="pipelines/ingestion/Dockerfile"
ENV_FILE="pipelines/ingestion/.env"

# Local host directory to store the vector database.
HOST_DB_PATH="${HOST_DB_PATH:-pipelines/ingestion/chroma_storage}"
case "$HOST_DB_PATH" in
  /*) : ;;                               
  *)  HOST_DB_PATH="$REPO_ROOT/$HOST_DB_PATH" ;;
esac

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ no existe $ENV_FILE (copiá .env.example)" >&2
  exit 1
fi

hr
echo "📂  [1/3] Seteo del host Chroma local"
hr
echo
mkdir -p "$HOST_DB_PATH"
echo

hr
echo "🐳  [2/3] Building de la imagen: $IMAGE_NAME"
hr
echo
docker build -f "$DOCKERFILE" -t "$IMAGE_NAME" .
echo

hr
echo "🚀  [3/3] Running de la ingesta (DB → Local Host)"
hr
echo
docker run --rm \
  --env-file "$ENV_FILE" \
  -v "$HOST_DB_PATH:/data/chroma_storage" \
  "$IMAGE_NAME"
echo

hr
echo "✅  Done!. Vector DB en: $HOST_DB_PATH"
hr
