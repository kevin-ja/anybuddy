#!/usr/bin/env bash
# Se ejecuta dentro de la instancia EC2
# Baja el indice (.tar.gz) desde S3 y lo extrae en la EBS del EC2.
# El contenedor de Chroma luego monta esa ruta como /data (imagen oficial, sin build).
set -euo pipefail

# SOURCE: S3_INDEX_URI: URI S3 del .tar.gz con el índice de Chroma a descargar 
# (ej. s3://anybuddy-artifacts/vector_db/chroma_storage.tar.gz)
: "${S3_INDEX_URI:?Define S3_INDEX_URI (p.ej. s3://bucket/approved/index.tar.gz)}"

# SINK: CHROMA_DATA_PATH: ruta en el host que se monta como /data de Chroma 
# (local: pipelines/ingestion/chroma_storage; prod: /data/chroma_storage en la EBS).
: "${CHROMA_DATA_PATH:=/data/chroma_storage}"
# Crea un archivo temporal donde descargará el .tar.gz.
TMP_TAR="$(mktemp /tmp/chroma-index.XXXXXX.tar.gz)"
# Al terminar el script (aunque falle), elimina el archivo temporal.
trap 'rm -f "$TMP_TAR"' EXIT

echo "📦 Bajando $S3_INDEX_URI ..."
# Descarga el archivo desde Amazon S3 al archivo temporal.
aws s3 cp "$S3_INDEX_URI" "$TMP_TAR"

echo "🗂  Extrayendo en $CHROMA_DATA_PATH ..."
# Crea una carpeta temporal donde descomprimirá la base de datos.
STAGING="${CHROMA_DATA_PATH}.new"
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Descomprime el archivo descargado en esa carpeta temporal.
tar -xzf "$TMP_TAR" -C "$STAGING"
rm -rf "${CHROMA_DATA_PATH}.old"

# Si ya existe una base de datos, la renombra como respaldo (.old).
[ -d "$CHROMA_DATA_PATH" ] && mv "$CHROMA_DATA_PATH" "${CHROMA_DATA_PATH}.old"

# Renombra la carpeta nueva para convertirla en la base de datos oficial.
mv "$STAGING" "$CHROMA_DATA_PATH"

echo "✅ Vector DB lista en $CHROMA_DATA_PATH"