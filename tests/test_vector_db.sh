#!/usr/bin/env bash
# Prueba rápida de conectividad contra el vector-db (Chroma) local.
set -euo pipefail

HOST="${CHROMA_HOST:-http://localhost:8000}"
TENANT="${CHROMA_TENANT:-default_tenant}"
DATABASE="${CHROMA_DATABASE:-default_database}"
BASE="$HOST/api/v2/tenants/$TENANT/databases/$DATABASE"

echo "==> Heartbeat ($HOST)"
curl -fsS "$HOST/api/v2/heartbeat" && echo

echo "==> Version"
curl -fsS "$HOST/api/v2/version" && echo

echo "==> Collections ($TENANT/$DATABASE)"
COLLECTIONS="$(curl -fsS "$BASE/collections")"
echo "$COLLECTIONS" | jq -r '.[] | "  - \(.name) (id=\(.id), dim=\(.dimension))"'

# --- Prueba funcional: query end-to-end contra la primera colección ---
COLL_ID="$(echo "$COLLECTIONS" | jq -r '.[0].id')"
COLL_NAME="$(echo "$COLLECTIONS" | jq -r '.[0].name')"
DIM="$(echo "$COLLECTIONS" | jq -r '.[0].dimension')"

if [ -z "$COLL_ID" ] || [ "$COLL_ID" = "null" ]; then
  echo "!! No hay colecciones: no se puede probar query." >&2
  exit 1
fi

echo "==> Query funcional sobre '$COLL_NAME' (dim=$DIM)"

# Embedding aleatorio de DIM dimensiones -> payload de query.
PAYLOAD="$(python3 - "$DIM" <<'PY'
import json, sys, random
dim = int(sys.argv[1])
emb = [round(random.uniform(-1, 1), 6) for _ in range(dim)]
print(json.dumps({
    "query_embeddings": [emb],
    "n_results": 3,
    "include": ["documents", "distances"],
}))
PY
)"

RESP="$(curl -fsS -X POST "$BASE/collections/$COLL_ID/query" \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD")"

# Validar que devolvió al menos 1 resultado.
N_HITS="$(echo "$RESP" | jq '.ids[0] | length')"
if [ "$N_HITS" -gt 0 ]; then
  echo "  OK: la query devolvió $N_HITS resultado(s)."
  echo "$RESP" | jq -r '.distances[0] as $d | .documents[0] // [] | to_entries[]
    | "  #\(.key+1) dist=\($d[.key]) doc=\(.value | tostring | .[0:80])"'
else
  echo "!! La query no devolvió resultados (¿colección vacía?)." >&2
  exit 1
fi

echo "==> OK: el vector-db responde y sirve queries correctamente."
