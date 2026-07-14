1. ¿"Ingestion con su Dockerfile, y luego el compose levanta los 3 + la vector DB"?

Casi, pero con dos matices importantes que tu propio ARCHITECTURE.md ya resuelve:

a) La vector DB NO se "construye" como contenedor desde ingestion. Esto es clave y lo dice la sección 3 y la tabla de la sección 4:

- Ingestion produce un artefacto de datos (index.tar.gz), no una imagen.
- En el EC2, el deploy baja ese .tar.gz → lo extrae en /data (EBS).
- El compose levanta la imagen oficial chromadb/chroma:1.5.9 y le monta /data como volumen.

O sea: el contenedor vector-db siempre es la imagen oficial de Chroma; lo único que cambia es la data montada. No hay un "build" tuyo de la vector DB. Tu frase "llamarlo y/o construirlo" → es montarlo como

b) Ingestion y el compose están desacoplados por S3, NO enciseño los trata como dos procesos independientes (secciones1 y 5):

- Proceso 1 (ingesta): corre en GitHub Actions (efímero, $0). Publica a S3 solo si pasa el gate de deepeval.
- Proceso 2 (servicio): los 3 contenedores en el EC2 vía do
- El "handoff" es S3, no una dependencia directa. El deploy del servicio puede correr sin re-ingestar, y la ingesta sin re-desplegar.

Entonces, sobre tu pregunta literal "¿debería haber un Dockerfile para ingestion?":

- No es obligatorio. GHA puede correr ingest.py directo con Python.
- Pero sí es recomendable containerizarlo — y por una razónntrato de compatibilidad): garantizas que la ingesta useexactamente chromadb 1.5.x y el mismo bge-base, evitando el bug de "el índice no se puede leer". Un Dockerfile fija eso de forma reproducible. Ese
contenedor lo corre el CI, no el compose.

✅ Conclusión: un solo compose para todo no — ingestion va orquesta solo los 3 servicios runtime (vector-db oficial +api + bot), con la vector DB montada como volumen, no construida.

2. ¿Dónde va el Dockerfile de ingestion y el compose? ¿En infra/?

La convención (y lo que ya hace tu repo) los separa por naturaleza:

┌───────────────────────────────┬─────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┐
│           Artefacto           │                Dónde                     Por qué                                 │
├───────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│                               │ pipelines/ingestion/Dockepi/Dockerfile, que ya existe ahí. El Dockerfile vive    │
│ Dockerfile de ingestion       │ (co-ubicado)                        │ junto al servicio que empaqueta: su contexto de build son esos          │
│                               │                                                                                  │
├───────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ Dockerfile del bot            │ apps/bot/Dockerfile (cuanHoy apps/bot/ está vacío.                               │
├───────────────────────────────┼─────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ docker-compose.yml (los 3     │ infra/                   questación/deploy, cruza varios servicios (api, bot,    │
│ servicios)                    │                                     │ vector-db). No pertenece a ninguno en particular → infra/.              │
├───────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ Workflows de GitHub Actions   │ .github/workflows/                  │ Obligatorio ahí por GitHub. Serían dos: ingest.yml y deploy.yml.        │
├───────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ Scripts de deploy (SSM, bajar │ infra/                              │ Mismo criterio que el compose.                                          │
│  tar.gz a /data)              │                                                                                  │
└───────────────────────────────┴─────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘

Sobre el "pipeline de GitHub Actions": dado el desacople, lo natural son dos workflows, no uno lineal:
1. ingest.yml — trigger: push a knowledge_base/ → corre ingtests → deepeval gate → publica a S3.
2. deploy.yml — trigger: tag/release → build api → ECR → SSM al EC2 → baja índice + docker compose up.

Puedes encadenar (que deploy se dispare tras un ingest exitoso), pero conceptualmente son separados — y así lo pide tu propia arquitectura.

Sobre lo de la API y model_loader

Correcto, es un pendiente aparte. Pero ojo a una tensión que veo en el ARCHITECTURE.md: la sección 4 dice "los 2 modelos viven dentro de la imagen
Docker" (horneados en build), mientras que model_loader loss que decidir cuál de los dos caminos sigue la API:

- Hornear en build: la API usa model_loader en el Dockerfil modelos dentro de la imagen → arranque rápido, sin S3 enruntime. Coincide con lo que dice el ARCHITECTURE.md.
- Bajar en runtime: la API llama a ensure_embedding_model/ecar → imagen ligera, pero depende de S3 vivo y un volumen de cache.

No lo decidas ahora; solo tenlo presente porque define cómo la API consume el paquete.

---
¿Quieres que te arme el esqueleto concreto? Puedo crear:
- pipelines/ingestion/Dockerfile,
- infra/docker-compose.yml con los 3 servicios (chroma ofic),
- y los dos workflows base en .github/workflows/.

Dime si lo hago y con qué nivel de detalle (esqueleto comentado vs. funcional), y reviso apps/api/app/config.py y el main.py para que el compose calce con cómo arranca hoy la API.