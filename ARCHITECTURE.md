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

El sistema se divide en **dos procesos** que corren en momentos y lugares distintos:

1. **Ingesta** — batch que vectoriza los documentos y publica el índice. Corre en **GitHub Actions** (cómputo $0).
2. **Servicio** — los 3 contenedores que atienden a los usuarios. Corre en **un solo EC2**.

- El handoff entre ambos es **S3** (buzón de artefactos versionado)
- El deploy del
servicio es **condicional** a que la ingesta haya pasado el quality gate de `deepeval`.

---

## 1. Vista general (ambos procesos)

```mermaid
flowchart TB
    subgraph P1["PROCESO 1 — INGESTA (GitHub Actions · efímero · $0)"]
        direction TB
        TRG1["Disparador:<br/>push a knowledge_base/<br/>o manual"]
        RUN["Runner efímero<br/>1. baja .txt<br/>2. ingest.py → bge-base → chroma_storage/<br/>3. deepeval = QUALITY GATE<br/>4. tar.gz + manifest → S3"]
        TRG1 --> RUN
    end

    subgraph AWS_STORAGE["Almacenamiento (AWS)"]
        direction LR
        S3K[("S3: anybuddy-knowledge<br/>versionado<br/>knowledge_base/faqs.txt")]
        S3A[("S3: anybuddy-artifacts<br/>versionado<br/>approved/&lt;ver&gt;/index.tar.gz<br/>+ manifest.json")]
    end

    subgraph P2["PROCESO 2 — SERVICIO (1 EC2 · always-on)"]
        direction TB
        TRG2["Disparador:<br/>tag/release o manual"]
        DEP["GitHub Actions (deploy)<br/>1. build api → ECR<br/>2. ssm send-command al EC2"]
        EC2["EC2 (3 contenedores)"]
        TRG2 --> DEP
    end

    EXT["Discord<br/>(~20 alumnos activos)"]
    OAI["OpenAI API"]

    S3K -- "lee documentos" --> RUN
    RUN -- "escribe SOLO si pasa el gate" --> S3A
    S3A -- "buzón: deploy baja el .tar.gz" --> DEP
    DEP --> EC2
    EC2 <-- "RAG / LLM" --> OAI
    EC2 <-- "WebSocket saliente" --> EXT

    classDef ci fill:#e8f0fe,stroke:#4285f4,color:#000
    classDef store fill:#fff4e5,stroke:#f5a623,color:#000
    classDef ext fill:#eafaf1,stroke:#27ae60,color:#000
    class P1,P2,RUN,DEP ci
    class S3K,S3A,AWS_STORAGE store
    class EXT,OAI ext
```

---

## 2. Proceso 1 — Ingesta (detalle)

Corre en un runner efímero de GitHub Actions.

### flujo 
    * El conocimiento fuente vive en un bucket de S3.
    * Cuando se agrega o modifica un documento, S3 genera un evento ObjectCreated.
    * Una AWS Lambda recibe ese evento y envía un repository_dispatch a GitHub con información del archivo afectado.
    * GitHub Actions ejecuta el pipeline de ingestión, chunking, generación de embeddings e indexación, idealmente solo para el documento que cambió.

Flujo completo

Usuario sube o modifica un documento en S3
                    ↓
           Evento ObjectCreated
                    ↓
                AWS Lambda
                    ↓
          repository_dispatch
                    ↓
       GitHub Actions (Workflow 1)
Ingestión → Chunking → Embeddings → Indexación


---

## 3. Proceso 2 — Servicio (detalle del EC2)

**1 EC2** en subred pública, Security Group **sin inbound**, administrado por **SSM**
(sin SSH, sin puerto 22). Dentro corren **3 contenedores** vía `docker compose`.

```mermaid
flowchart TB
    subgraph GHA["GitHub Actions (deploy)"]
        BUILD["docker build api"]
        SSM["aws ssm send-command"]
    end

    ECR[("ECR<br/>imagen api:&lt;tag&gt;<br/>ligera (sin modelos)")]
    S3A[("S3: anybuddy-artifacts<br/>approved/&lt;ver&gt;/index.tar.gz")]
    SSMP[("SSM Parameter Store<br/>OPENAI_API_KEY<br/>DISCORD_BOT_TOKEN")]

    subgraph EC2["EC2 (t3.small/medium) — subred pública, SIN inbound"]
        direction TB
        AGENT["SSM Agent<br/>baja approved/ → /data<br/>docker compose pull && up -d"]

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
    ECR -- "docker pull" --> DC
    S3A -- "buzón (no lectura en vivo)" --> AGENT
    SSMP -- "inyecta secretos en runtime" --> DC
    API <-- "LLM" --> OAI
    BOT <-- "WebSocket SALIENTE" --> DISCORD

    classDef store fill:#fff4e5,stroke:#f5a623,color:#000
    classDef ext fill:#eafaf1,stroke:#27ae60,color:#000
    classDef compute fill:#e8f0fe,stroke:#4285f4,color:#000
    class ECR,S3A,SSMP,EBS,DATA store
    class OAI,DISCORD ext
    class VDB,API,BOT compute
```

---

## 4. Quién vive dónde

| Componente | Dónde vive | Cómo se comunica |
|---|---|---|
| **Ingesta** (`ingest.py` + deepeval) | GitHub Actions (efímero) | lee S3-knowledge, escribe S3-artifacts |
| **Índice vectorial** (`chroma_storage`) | nace en CI → **S3** → se copia al **EBS** del EC2 | Chroma lo monta como `/data` |
| **Documentos** (`faqs.txt`) | **S3-knowledge** (versionado) | CI lo baja en cada ingesta |
| **Los 2 modelos** (embedder + reranker) | **S3** → cache en volumen del EC2 (bajados al arrancar, vía `model_loader`) | se cargan en RAM al arrancar la API |
| **vector-db** (Chroma 1.5.9) | contenedor en el **EC2** | HTTP con la API (red local) |
| **api** (FastAPI) | contenedor en el **EC2** | HTTP con Chroma y con el bot; llama a OpenAI |
| **bot** (discord.py) | contenedor en el **EC2** | HTTP a la API; WebSocket **saliente** a Discord |
| **Secretos** | **SSM Parameter Store** | inyectados al EC2 en runtime |

---

## 5. Las 3 ideas clave

1. **Gate condicional:** el deploy solo es posible porque existe algo en `approved/`, y a
   `approved/` solo se llega si **deepeval pasó**. Ahí se materializa que el "proceso 2
   depende del proceso 1".
2. **S3 es buzón, no fuente viva:** Chroma lee de `/data` (EBS), nunca de S3 directo.
   S3 solo entrega el `.tar.gz`.
3. **EC2 sin puertas abiertas:** ningún inbound. El bot sale solo hacia Discord; la
   administración entra por SSM. Sin NGINX, sin Load Balancer, sin NAT Gateway.

---

## 6. Contrato de compatibilidad (crítico)

Ingesta y servicio **deben** usar versiones idénticas, o el índice no se podrá leer:

- `chromadb` **pineado** a `1.5.x` (igual que el server `chromadb/chroma:1.5.9`).
- Mismo modelo de embedding: `BAAI/bge-base-en-v1.5`.

El `manifest.json` que viaja junto al `.tar.gz` registra `{embedding_model,
chromadb_version, git_sha}` para que el servicio **valide en el arranque** que coincide
con lo que él corre, y falle rápido si no.

---

## 7. Costo estimado

| Recurso | Costo aprox. |
|---|---|
| 1 × EC2 t3.small (always-on) | ~$15/mes (t3.medium ~$30 si la RAM lo exige) |
| Ingesta en GitHub Actions | $0 (free tier / repos privados) |
| S3 + ECR | centavos |
| deepeval (gpt-4o-mini por corrida) | fracciones de centavo |
| NAT Gateway | **$0** (se evita: subred pública egress-only) |

**Total realista: ~$15–30/mes** para todo el sistema sirviendo a ~20 usuarios activos.


---

```mermaid
graph TD
    %% Definición de Estilos
    classDef process fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef storage fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    classDef gate fill:#ffebee,stroke:#c62828,stroke-width:2px;

    Source[S3: knowledge_base] --> Runner(GitHub Actions: Runner Efímero)
    
    subgraph Procesamiento
        Runner --> B[Vectorización: bge-base]
        B --> C[Indexación: ChromaDB]
    end
    
    C --> Gate{Quality Gate: deepeval}
    
    Gate -- Falla --> Stop((Abortar))
    Gate -- Pasa --> Pack[Empaquetar: index.tar.gz + manifest.json]
    
    Pack --> Target[(S3: anybuddy-artifacts)]

    %% Aplicar estilos
    class Runner,B,C,Pack process;
    class Source,Target storage;
    class Gate,Stop gate;
```