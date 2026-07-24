# Arquitectura — AnyBuddy Assistant

```mermaid
graph TD
    %% Definición de Estilos y Clases
    classDef awsNode fill:#f9f9f9,stroke:#FF9900,stroke-width:2px,color:#333;
    classDef container fill:#e1f5fe,stroke:#0288d1,stroke-width:1.5px,color:#01579b;
    classDef storage fill:#efebe9,stroke:#5d4037,stroke-width:1.5px,color:#3e2723;
    classDef external fill:#f3e5f5,stroke:#7b1fa2,stroke-width:1.5px,color:#4a148c;

    %% Bloque Principal: Instancia EC2
    subgraph EC2 ["☁️ Instancia AWS EC2 (Subred Pública / SG: Zero Inbound)"]

        %% Contenedores
        VDB["🐳 vector-db<br>(Chroma 1.5.9 Oficial)"]:::container
        API["🐳 api<br>(FastAPI + Modelos en RAM)"]:::container
        BOT["🐳 bot<br>(discord.py)"]:::container

        %% Almacenamiento Local
        EBS[("💾 Volumen Local EBS<br>/data (Índice extraído de S3)")]:::storage

        %% Interconexiones internas
        VDB <-->|HTTP :8000<br>Red Local| API
        API <-->|HTTP :8000<br>Red Local| BOT
        VDB -->|Monta /data| EBS
    end

    %% Entidades Externas
    OPENAI["🧠 OpenAI API<br>(Llamadas de LLM)"]:::external
    DISCORD["💬 Discord Servers<br>(~20 alumnos activos)"]:::external

    %% Conexiones Salientes (Egress)
    API ====>|HTTPS Saliente| OPENAI
    BOT ====>|WebSocket Saliente| DISCORD

    %% Aplicar estilo a la EC2
    style EC2 fill:#ffffff,stroke:#FF9900,stroke-width:3px,color:#232F3E;
```

Sistema backend de un bot de Discord que asiste a una comunidad de ~50 alumnos
(~20 activos) con preguntas académicas, vía RAG.

El sistema se divide en **dos procesos** que corren en momentos distintos, pero
**en la misma máquina** (un solo EC2):

1. **Ingesta** — batch efímero que vectoriza los documentos y publica el índice.
   Corre como contenedor *one-shot* (`docker run --rm`) **en el EC2**, disparado
   por un cambio de artefacto en S3.
2. **Servicio** — los 3 contenedores permanentes que atienden a los usuarios
   (`restart: unless-stopped`). Corren en **el mismo EC2**.

- El handoff entre ambos es **S3** (buzón de artefactos, versionado recomendado).
- La regla mental que gobierna todo: **código = build; artefacto = run.**
  Cambiar *código* dispara un **build de imágenes Docker** (GitHub Actions → ECR); cambiar
  un *artefacto* (dato/modelo en S3) dispara un **run** de la imagen ya construida
  (evento S3 → EC2). Al cambiar un artefacto **no se compila nada**.

---

## 1. Vista general (ambos procesos)

```mermaid
flowchart TB
    subgraph BUILD_PLANE["PLANO DE BUILD — CÓDIGO cambia (GitHub Actions · efímero)"]
        direction TB
        TRG0["Disparador:<br/>push de código"]
        GHA["Runner efímero:<br/>build docker images (api + bot + ingestion)<br/>→ push a ECR"]
        TRG0 --> GHA
    end

    subgraph AWS_STORAGE["Almacenamiento (AWS · bucket ÚNICO anybuddy-artifacts)"]
        direction TB
        ECR[("ECR<br/>anybuddy-{api,bot,ingestion}")]
        S3[("S3: anybuddy-artifacts (versionado recomendado)<br/>knowledge_base/faqs.txt<br/>models/embedding_model.tar.gz<br/>vector_db/chroma_storage.tar.gz")]
    end

    subgraph RUN_PLANE["PLANO DE RUN — ARTEFACTO cambia (1 EC2 · always-on)"]
        direction TB
        TRG1["Disparador:<br/>evento S3 (ObjectCreated) en<br/>knowledge_base/ o models/"]
        EVT["EventBridge → SSM RunCommand<br/>(sin Lambda; tentativo)"]
        EC2["EC2:<br/>1. corre imagen INGESTA (--rm) → vector_db → S3<br/>2. fetch_vector_db.sh (baja vector_db)<br/>3. docker compose pull + recrea los contenedores (chroma, api, bot)"]
        TRG1 --> EVT --> EC2
    end

    EXT["Discord<br/>(~20 alumnos activos)"]
    OAI["OpenAI API"]

    GHA -- "push imágenes" --> ECR
    ECR -- "docker pull (instance profile)" --> EC2
    S3 -- "lee knowledge_base/ + models/" --> EC2
    EC2 -- "escribe vector_db/" --> S3
    EC2 <-- "RAG / LLM" --> OAI
    EC2 <-- "WebSocket saliente" --> EXT

    classDef ci fill:#e8f0fe,stroke:#4285f4,color:#000
    classDef store fill:#fff4e5,stroke:#f5a623,color:#000
    classDef ext fill:#eafaf1,stroke:#27ae60,color:#000
    class BUILD_PLANE,GHA ci
    class RUN_PLANE,EVT,EC2 ci
    class ECR,S3,AWS_STORAGE store
    class EXT,OAI ext
```

---

## 2. Proceso 1 — Ingesta (detalle)

Corre como **contenedor efímero en el EC2** (`docker run --rm` de la imagen
`anybuddy-ingestion` bajada de ECR). **No** corre en GitHub Actions: bajo el
modelo "código = build; artefacto = run", GitHub Actions solo construye
imágenes; la ingesta es un *run* de artefacto y sucede en el EC2.

### flujo

* El conocimiento fuente y el modelo de embedding viven en el bucket único
    anybuddy-artifacts (prefijos knowledge_base/ y models/).
* Cuando se agrega o modifica un artefacto, S3 genera un evento ObjectCreated.
* EventBridge (filtrado a los prefijos knowledge_base/ y models/) reacciona
    y ejecuta un SSM RunCommand contra el EC2. (Se descartó Lambda salvo que se
    necesite lógica condicional; decisión tentativa: sin Lambda.)
* El EC2 corre la imagen de ingesta one-shot: chunking, embeddings e
    indexación con Chroma, y sube el índice comprimido a S3 (vector_db/).

Flujo completo

```
[S3: knowledge_base/ o models/] -(evento ObjectCreated)-> [EventBridge (filtro por prefijo)] -(RunCommand)-> [SSM] -(envía comando)-> [EC2] -(docker run --rm anybuddy-ingestion: chunking, embeddings, indexación Chroma)-> [vector_db: chroma_storage.tar.gz] -(subir)-> [S3: vector_db/] -(fetch + recrea)-> [Contenedores: chroma, api, bot]
```

> **Nota — Quality gate (deepeval): recomendado, aún NO incorporado.**
> El plan contempla un gate de calidad con `deepeval` que valide el índice
> **antes** de subirlo a S3 (y aborte la subida si no pasa). La dependencia ya
> está declarada, pero **el gate todavía no está implementado** en el pipeline.
> Es **recomendable pero no mandatorio**: sin él, la ingesta sube el índice sin
> validación de calidad automática.

---

## 3. Proceso 2 — Servicio (detalle del EC2)

**1 EC2** en subred pública, Security Group **sin inbound**, administrado por **SSM**
(sin SSH, sin puerto 22). Autentica contra ECR y S3 con su **instance profile**
(IAM, **cero access keys** en la máquina). Dentro corren **3 contenedores** vía
`docker compose` (con `docker-compose.prod.yml`, que usa `image:` de ECR en vez
de `build:`).

```mermaid
flowchart TB
    subgraph GHA["GitHub Actions (build — CÓDIGO cambia)"]
        BUILD["runner efímero:<br/>build docker images (api + bot + ingestion)"]
    end

    subgraph TRIG["Disparo del deploy (ARTEFACTO cambia)"]
        SSM["EventBridge → SSM send-command"]
    end

    ECR[("ECR<br/>anybuddy-{api,bot,ingestion}:&lt;tag&gt;")]
    S3[("S3: anybuddy-artifacts<br/>vector_db/chroma_storage.tar.gz")]
    ENV[(".env.prod (en el EC2)<br/>OPENAI_API_KEY<br/>DISCORD_BOT_TOKEN")]

    subgraph EC2["EC2 (t3.small) — subred pública, SIN inbound"]
        direction TB
        AGENT["SSM Agent:<br/>fetch_vector_db.sh → /data<br/>docker compose pull + recrea los contenedores<br/>(NUNCA build)"]

        subgraph DC["docker compose — 3 contenedores"]
            direction LR
            VDB["vector-db<br/>chroma 1.5.9<br/>(imagen oficial)"]
            API["api<br/>fastapi<br/>carga embedder + reranker en RAM"]
            BOT["bot<br/>discord.py"]
            API <-- "HTTP :8000" --> VDB
            BOT <-- "HTTP :8000" --> API
        end

        subgraph EBS["EBS (disco del EC2)"]
            DATA["/data ← chroma_storage<br/>(índice bajado del S3)"]
        end
        VDB -- "monta /data" --> DATA
    end

    OAI["OpenAI API"]
    DISCORD["Discord<br/>(~20 alumnos)"]

    BUILD --> ECR
    SSM --> AGENT
    ECR -- "docker pull (instance profile)" --> DC
    S3 -- "buzón (no lectura en vivo)" --> AGENT
    ENV -- "inyecta secretos en runtime" --> DC
    API <-- "LLM" --> OAI
    BOT <-- "WebSocket SALIENTE" --> DISCORD

    classDef store fill:#fff4e5,stroke:#f5a623,color:#000
    classDef ext fill:#eafaf1,stroke:#27ae60,color:#000
    classDef compute fill:#e8f0fe,stroke:#4285f4,color:#000
    class ECR,S3,ENV,EBS,DATA store
    class OAI,DISCORD ext
    class VDB,API,BOT compute
```

---

## 4. Quién vive dónde

| Componente | Dónde vive | Cómo se comunica |
|---|---|---|
| **Ingesta** (`ingest.py`) | contenedor efímero (`--rm`) **en el EC2** | lee `knowledge_base/` + `models/` de S3, escribe `vector_db/` en S3 |
| **Índice vectorial** (`chroma_storage`) | nace en la ingesta → **S3** → se copia al **EBS** del EC2 | Chroma lo monta como `/data` |
| **Documentos** (`faqs.txt`) | **S3** `anybuddy-artifacts/knowledge_base/` (versionado recomendado) | la ingesta lo baja en cada corrida |
| **Modelo de embedding** | **S3** `models/embedding_model.tar.gz` → cache en el EBS del EC2 (vía `model_loader`) | se carga en RAM al arrancar la API |
| **vector-db** (Chroma 1.5.9) | contenedor en el **EC2** | HTTP con la API (red local) |
| **api** (FastAPI) | contenedor en el **EC2** | HTTP con Chroma y con el bot; llama a OpenAI |
| **bot** (discord.py) | contenedor en el **EC2** | HTTP a la API; WebSocket **saliente** a Discord |
| **Imágenes** (api/bot/ingestion) | **ECR** `anybuddy-{api,bot,ingestion}` | el EC2 hace `pull` con su instance profile |
| **Secretos** | **`.env.prod`** en el EC2 | inyectados a los contenedores en runtime |

---

## 5. Las 3 ideas clave

1. **Código = build; artefacto = run.** Cambiar código dispara un *build* de
   imágenes en GitHub Actions (→ ECR); cambiar un artefacto en S3 dispara un *run*
   de la imagen ya construida (evento S3 → EventBridge → SSM → EC2). El EC2 **nunca
   ve el código fuente**: solo baja imágenes ya hechas de ECR.
2. **S3 es buzón, no fuente viva:** Chroma lee de `/data` (EBS), nunca de S3 directo.
   S3 solo entrega el `.tar.gz` (`vector_db/chroma_storage.tar.gz`).
3. **EC2 sin puertas abiertas:** ningún inbound. El bot sale solo hacia Discord; la
   administración entra por SSM; autentica contra ECR/S3 con instance profile. Sin
   NGINX, sin Load Balancer, sin NAT Gateway, sin SSH.

---

## 6. Contrato de compatibilidad (crítico)

Ingesta y servicio **deben** usar versiones idénticas, o el índice no se podrá leer:

- `chromadb` **pineado** a `1.5.9` en ambos lados (igual que el server
  `chromadb/chroma:1.5.9`). **Esto ya está en vigor** (ambos `requirements.txt`).
- Mismo modelo de embedding: `BAAI/bge-base-en-v1.5`.

> **Recomendado, aún NO incorporado — validación por `manifest.json`.**
> El plan es que un `manifest.json` viaje junto al `.tar.gz` registrando
> `{embedding_model, chromadb_version, git_sha}`, y que el servicio **valide en el
> arranque** que coincide con lo que él corre (y falle rápido si no). Hoy **ni el
> `manifest.json` ni la validación en arranque están implementados**: la garantía
> de compatibilidad descansa únicamente en el pin manual de versiones de arriba.
> Es **recomendable pero no mandatorio**.

---

## 7. Costo estimado

| Recurso | Costo aprox. |
|---|---|
| 1 × EC2 t3.small (always-on) | ~$15/mes (t3.medium ~$30 si la RAM lo exige) |
| Ingesta (contenedor `--rm` en el mismo EC2) | $0 extra (reusa la caja que ya existe) |
| Build en GitHub Actions | $0 (free tier) |
| S3 + ECR | centavos |
| NAT Gateway | **$0** (se evita: subred pública egress-only) |

**Total realista: ~$15–30/mes** para todo el sistema sirviendo a ~20 usuarios activos.

---

```mermaid
graph TD
    %% Definición de estilos
    classDef process fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef storage fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    classDef gate fill:#ffebee,stroke:#c62828,stroke-width:2px;

    Source["S3: knowledge_base / models"] --> Trigger["Evento S3 → EventBridge → SSM"]
    Trigger --> Runner["EC2: docker run --rm ingestion"]

    subgraph Procesamiento
        Runner --> B["Vectorización: bge-base"]
        B --> C["Indexación: ChromaDB 1.5.9"]
    end

    C --> Gate{"Quality Gate\nDeepeval\n(Recomendado, aún no incorporado)"}

    Gate -- Falla --> Stop(("Abortar subida"))
    Gate -- Pasa --> Pack["Empaquetar: chroma_storage.tar.gz"]

    Pack --> Target[("S3: anybuddy-artifacts/vector_db/")]

    %% Aplicar estilos
    class Runner,B,C,Pack process;
    class Source,Target storage;
    class Gate,Stop gate;
```
