---
CONTEXTO — Proyecto anybuddy_2.0 (RAG bot Discord)
Dir: /Users/kevinjesusapari/CodeHub/anybuddy_2.0

META: Automatizar el pipeline de ingesta event-driven:
S3 (doc nuevo) → evento ObjectCreated → AWS Lambda → repository_dispatch
→ GitHub Actions Workflow 1 (ingesta: chunking/embeddings/index → S3)
→ GitHub Actions Workflow 2 (deploy a EC2 vía SSM).

PLAN POR NIVELES (se construye de abajo hacia arriba; la Lambda es lo ÚLTIMO):
- N0  Sustrato S3 (buckets + modelo)............... ✅ HECHO
- N1  Auth GitHub→AWS vía OIDC.................... 🔧 CASI (ver abajo)
- N2  ingest.yml corriendo a mano (workflow_dispatch)... ⬜ pendiente
- N3  deploy.yml + encadenado (workflow_run)........... ⬜ pendiente
- N4  Lambda + evento S3 + repository_dispatch......... ⬜ pendiente (lo último)
Pospuesto a propósito (requiere tocar código): deepeval, manifest.json, ingesta incremental por-documento.

DATOS CLAVE:
- Región AWS: us-east-2
- Bucket único: anybuddy-artifacts (knowledge en knowledge_base/, modelo en models/, output en approved/)
- GitHub user: kevin-ja ; repo previsto: kevin-ja/anybuddy_2.0 (AÚN NO EXISTE)
- Ya renombramos en código: ARTIFACTS_S3_PREFIX → VECTOR_DB_S3_PREFIX (config.py:38 y sinks.py:42).
  En prod hay que setear VECTOR_DB_S3_BUCKET=anybuddy-artifacts y VECTOR_DB_S3_PREFIX=approved.

DÓNDE PARAMOS (dentro de N1):
- ✅ Creado el OIDC identity provider en IAM (token.actions.githubusercontent.com, aud sts.amazonaws.com).
- ✅ Creado el role "anybuddy-gha-ingest" con custom trust policy (sub: repo:kevin-ja/anybuddy_2.0:*, wildcard a propósito por ahora).
- ✅ Agregada inline policy "ingest-s3-access" (GetObject a knowledge_base/* y models/*; PutObject+AbortMultipartUpload a approved/*).
- ⬜ FALTA copiar el ARN del role y guardarlo como variable de repo AWS_ROLE_ARN (bloqueado: el repo GitHub no existe todavía).

BLOQUEO / PRÓXIMO PASO REAL = crear el repo GitHub, PERO antes:
- ⚠️ NO hay .gitignore en la raíz y el ./.env tiene claves REALES (AWS, OpenAI, Discord).
  1) Crear .gitignore raíz que ignore .env (Claude ya propuso el contenido).
  2) ROTAR las claves expuestas (AWS + Discord token mínimo; la AWS access key ya no hace falta con OIDC).
  3) git init → commit (verificar que .env NO aparezca) → crear kevin-ja/anybuddy_2.0 → push.
  4) Agregar variable AWS_ROLE_ARN en Settings→Secrets and variables→Actions→Variables.
Luego: arrancar N2 (escribir ingest.yml).
