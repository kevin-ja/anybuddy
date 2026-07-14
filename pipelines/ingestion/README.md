# Ingestion

- **Proceso por lotes** (Corre, hace su trabajo, deja el producto y termina) que 
construye la base de datos vectorial

- En producción corre en **GitHub Actions**
- En local corre cuando quieres regenerar el índice localmente.

## Flujo del proceso.

La lógica del flujo esta plasmado en **`ingest.py`**

1. **Resuelve los inputs** (`sources.py`): Se asegura de tener el `faqs.txt` y el
   modelo de embedding a disposición.
2. **Chunking**: Divide el documento en fragmentos pequeños
   bajo la sgte jerarquia: párrafos → líneas → oraciones.
3. **Vectoriza**: pasa cada fragmento por el modelo de embedding y obtiene un
   vector por fragmento.
4. **Guarda en ChromaDB**: Genera la DB vectorial, esto es, escribe los vectores en `chroma_storage/`.
5. **Publica el output** (`sinks.py`): en local lo deja en `chroma_storage/`; en
   producción comprime esa carpeta a `.tar.gz` y la sube a S3 (el entregable final
   que consume `api/`).


```
   INPUTS                       INGESTION PROCCESS               OUTPUT (SINK)
┌──────────────┐
│  faqs.txt    │──┐
│ (documentos) │  │         ┌────────────────────┐    ┌─────────────────┐   ┌──────────────┐
└──────────────┘  ├────────▶│ 1. chunking text   │───▶│ chroma_storage  │──▶│ S3 (.tar.gz)  │
┌──────────────┐  │         │ 2. vectoriza       │    │   (Vector DB)   │   │ solo en prod  │
│ modelo de    │──┘         │ 3. guarda          │    └─────────────────┘   └──────────────┘
│ embedding    │            └────────────────────┘      (sources.py)          (sinks.py)
└──────────────┘                                         siempre local         prod: sube
```


## Environments

Una sola variable manda: **`APP_ENV`** (en `config.py`).

| Recurso | `APP_ENV=local` | `APP_ENV=production` |
|---|---|---|
| **modelo de embedding** | se baja de **S3** *[^1]*| se baja de **S3** (mismo bucket) |
| **faqs.txt** | se lee **del disco** *[^2]* | se baja de **S3** |
| **output (vector db)** | se construye en `chroma_storage/` y **queda local** | se construye en `chroma_storage/` y se **sube a S3** |


- *[^1]* El **modelo** es un binario fijo que no se modifica (puede reemplazarse 
pero no modificarse), Por lo tanto se baja siempre del mismo lugar (Bucket S3). 
Así no hay dos caminos que mantener. Es **idempotente**: si ya está en tu 
`.models_cache/`, no lo vuelve a bajar.
- *[^2]* El **`faqs.txt`** Normalmente SI es editable, por lo que en local lo 
lees de tu disco; solo en producción viene de S3.


## Estructura del directorio
```
pipelines/ingestion/
├── src/
│   ├── config.py     # toda la configuración (APP_ENV, rutas, buckets S3)
│   ├── sources.py    # SOURCE: decide de dónde salen los inputs (local vs S3)
│   ├── sinks.py      # SINK: comprime la DB vectorial y la sube a AWS S3 (solo prod)
│   ├── utils.py      # compresión .tar.gz: compress_dir / extract_tar
│   ├── ingest.py     # el pipeline: trocea, vectoriza, guarda y publica
│   ├── requirements.txt # dependencias principales
│   └── requirements.in # dependencias principales y secundarias
├── knowledge_base/   # ARTIFACT: local: faqs.txt - (gitignored: no versionado) [^3]
├── .models_cache/    # ARTIFACT: local: model embedding - (gitignored: no versionado) [^3]
├── chroma_storage/   # ARTIFACT: local: base vectorial - (gitignored: no versionado) [^3]
├── .env              # SECRETS : secretos/config - (gitignored: no versionado) [^3]
└── .env.example      # plantilla de .env
```

- *[^3]* **Están en `.gitignore` a propósito.** Los tres directorios de datos son
artefactos (data y binarios) que en producción viven en S3, no en el repo; el
`.env` se ignora por contener secretos.


### ¿De dónde sale la descarga del modelo?

⚠️ > La lógica para descargar el modelo de S3 **no vive en este modulo**, sino que está en el paquete
compartido **`packages/model_loader`**, porque el servicio `api/` también lo
necesita. Este pipeline solo lo llama:


```python
ensure_embedding_model(cache_dir, bucket=..., key=...)
```

* `config.py` (de este pipeline) decide **qué** bucket y **qué** modelo;
* `model_loader` sabe **cómo** bajarlo. Si mañana cambias de AWS a otro proveedor,
solo se toca `model_loader` — este pipeline ni se entera.

---

## Inputs: `sources.py`

* este submódulo pone a disposición, de forma desacoplada y agnóstica, los inputs (binarios, artefactos) que el proceso de ingestion necesita.
* concretamente los inputs son 2 elementos:
   * el modelo de embedding
   * la fuente de datos a vectorizar (`faqs.txt`)

* el OUTPUT (la base de datos vectorial, Chroma DB) NO se resuelve aquí: vive en el sink (`sinks.py`, más adelante).

* la importancia de este submódulo reside en que `ingest.py` queda **agnóstico a la infraestructura**: este submódulo hace el trabajo sucio.


### Logica de implementación

`ensure_inputs()` resuelve los dos inputs por separado, porque se comportan
distinto:

1. **El modelo de embedding → siempre de S3.**
   Llama a `ensure_embedding_model(...)` (del paquete `model_loader`), pasándole el
   bucket y la key que vienen de `config.py`. Es idempotente: si ya está en
   `.models_cache/`, no baja nada. Esto es igual en local y en producción.

2. **El `faqs.txt` → depende del entorno** (`_resolve_knowledge()`):
   - `APP_ENV=local`: verifica que el archivo exista en disco. Si no está, **falla
     rápido** con un mensaje claro ("coloca tu faqs.txt aquí").
   - `APP_ENV=production`: lo **baja de S3** al disco.

   En ambos casos termina devolviendo una ruta local — el mismo contrato.


---

## Outputs: `sinks.py` (el OUTPUT):
* publica la base de datos vectorial (el output del ingestion) en un bucket S3.
* corre siempre, pero **solo sube a S3 en modo producción**:
   - **`APP_ENV=local`**: no se sube nada. La DB se queda en `chroma_storage/`, lista
   para iterar. `publish_outputs()` devuelve `None`.
   - **`APP_ENV=production`**: el `chroma_storage/` **no es el entregable final**; el
   entregable es ese índice comprimido y publicado en S3, listo para que `api/` lo
  consuma. Devuelve la **URI `s3://`** del artefacto publicado.


## Cómo se relacionan los scripts entre sí

Los archivos de `src/` forman una cadena con responsabilidades que no se
pisan: **configurar → conseguir → procesar → publicar**.

```
config.py  ──▶  sources.py  ──▶  ingest.py  ──▶  sinks.py
(el QUÉ/DÓNDE)   (el CONSEGUIR)   (el HACER)      (el PUBLICAR)
                                       │               │  usa utils.py (.tar.gz)
                                       ▼               ▼
                                 chroma_storage/   s3://…/chroma_storage.tar.gz
```

### El rol de cada uno

| Script | Responsabilidad | Analogía |
|---|---|---|
| `config.py` | Define **qué** valores se usan: `APP_ENV`, rutas locales, buckets y keys de S3. No hace nada, solo declara. | La **lista de la compra** |
| `sources.py` | Usa esa config para **conseguir** los inputs y dejarlos en disco como rutas locales. | El que va al **mercado** |
| `ingest.py` | Toma esos inputs y **hace el trabajo**: trocea, vectoriza y guarda en ChromaDB. | El que **cocina** |
| `sinks.py` | Toma el output local, lo **comprime y publica** en S3 (se apoya en `utils.py`). | El que **empaqueta y envía** |

### El flujo, paso a paso

1. **`ingest.py` arranca** y lo primero que hace es importar `settings` desde
   `config.py` (lee tu `.env`) y llamar a `ensure_inputs(settings)` de `sources.py`.
2. **`sources.py` lee de `config.py`** qué bucket/rutas usar y, según `APP_ENV`,
   consigue el `faqs.txt` y el modelo. Para el modelo se apoya en el paquete
   externo **`model_loader`** (la descarga real). Devuelve un `ResolvedInputs`.
3. **`ingest.py` recibe las rutas** y ejecuta su lógica pura de procesamiento
   (chunking → embeddings → ChromaDB), escribiendo el resultado en
   `chroma_storage/` (la ruta que también salió de `config.py`).
4. **`ingest.py` llama a `publish_outputs(settings)` de `sinks.py`**: en local no
   hace nada (la DB queda en `chroma_storage/`); en producción comprime esa carpeta
   con `utils.py`, sube el `.tar.gz` a S3 y devuelve la URI.

### La dirección de las dependencias (importante)

Las flechas van en **una sola dirección**, y eso es a propósito:

- `config.py` **no importa a nadie** (es la base, solo declara).
- `sources.py` **importa `config`** y `model_loader`, pero **no importa `ingest`**.
- `sinks.py` **importa `config`, `utils` y `model_loader`**, pero **no importa
  `ingest`** (también es agnóstico al pipeline).
- `utils.py` **no importa a nadie del pipeline** (compresión pura y reutilizable).
- `ingest.py` **importa `config`, `sources` y `sinks`**, pero nadie lo importa a él
  (es el punto de entrada).

Esto significa que puedes **cambiar de dónde salen los inputs** (editar
`sources.py` o un valor en `config.py`) **sin tocar la lógica de procesamiento**
de `ingest.py`, y viceversa. Cada pieza se entiende y se prueba por separado.


## como correrlo

### context build
``` bash
cd /Users/kevinjesusapari/CodeHub/anybuddy_2.0        # ← contexto = deberia ser la raíz

docker build \
  -f pipelines/ingestion/Dockerfile \                 # ← dónde está el Dockerfile
  -t anybuddy-ingestion \
  .                                                    # ← el "." = build context = raíz


- "." (context) = qué archivos puede ver Docker
- "-f" = qué receta usar → el Dockerfile dentro de ingestion/
```

### local 
#### 1. Construir la imagen

Desde la raíz del repo

cd /Users/kevinjesusapari/CodeHub/anybuddy_2.0

docker build \
  -f pipelines/ingestion/Dockerfile \
  -t anybuddy-ingestion \
  .

#### 2. Levantar el contenedor con el .env

El flag es --env-file. Ahí van las credenciales AWS + el resto de config:

docker run --rm \
  --env-file pipelines/ingestion/.env \
  anybuddy-ingestion

- --rm → borra el contenedor al terminar (es un job, no un servicio).
- --env-file → inyecta cada línea CLAVE=valor del .env como variable de entorno dentro del contenedor. Así boto3 encuentra AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY por la credential chain.

alternativamente

docker run --rm \
  --env-file pipelines/ingestion/.env \
  -e APP_ENV=production \
  anybuddy-ingestion
(el -e sobreescribe lo que venga del .env).

----

## aplanar los archivos:
1. Copia el snapshot resolviendo symlinks (la -L es la clave):
cd models--BAAI--bge-base-en-v1.5

cp -RL snapshots/a5beb1e3e68b9ab74eb54cfd186867f64f240e1a/ /tmp/embedding_model_flat
La -L hace que copie el contenido real de los blobs, no los symlinks.

2. Verifica que quedó plano y con archivos reales (no symlinks):
ls -la /tmp/embedding_model_flat
Debes ver config.json, model.safetensors, tokenizer.json, modules.json, la subcarpeta 1_Pooling/, etc. — y que no empiecen con l (symlink) ni con flecha ->.


Entra a la carpeta aplanada:

tar -czf ../embedding_model.tar.gz .


❯ docker run --rm \                                                                   
  --env-file pipelines/ingestion/.env \
  anybuddy-ingestion     
📦 Descargando models/embedding_model.tar.gz desde s3://anybuddy-artifacts ...
📂 embedding_model listo en: /app/pipelines/ingestion/models/embedding_model
📖 Leyendo el knowledge base desde /app/pipelines/ingestion/knowledge_base/faqs.txt...
🧠 Ejecutando el Chunking Inteligente Nativo...
🧠 Cargando el modelo de embedding...
Loading weights: 100%|██████████| 199/199 [00:00<00:00, 15650.39it/s]
🧬 Generando vectores para 24 fragmentos...
🗄️ Conectando al almacenamiento local de ChromaDB...
✅ ¡Ingesta completada!
📤 Publicando el indice vectorial en S3...
📁 output local listo en /data/chroma_storage (no se sube a S3)