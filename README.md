# anybuddy 2.0

## Flujo CI/CD — vista general

Todo el pipeline se entiende con una distinción, y conviene tenerla clara antes de mirar
el diagrama: **api y bot son estado; la ingesta es un evento.**

- **api y bot** son servicios permanentes. Desplegarlos significa dejarlos *corriendo con
  la imagen nueva*. Eso es un **estado deseado**, y `docker compose up -d` sabe llegar solo:
  compara la imagen del contenedor con la que acaba de bajar, ve que cambió y lo recrea.
- **La ingesta** arranca, trabaja ~20 min y muere. No hay ningún contenedor suyo corriendo
  que haya que corregir, así que `up -d` no tiene nada que comparar ni nada que hacer. Su
  producto no es un contenedor: es el `vector_db` que queda en S3.

De ahí sale la regla que gobierna el pipeline: **una imagen nueva es una receta nueva, no
un plato cocinado.** Para api y bot esas dos cosas son lo mismo, porque la imagen *es* lo
que se sirve. 

Para la ingesta hay un paso en el medio que ningún `up -d` puede deducir:
**hay que ejecutarla.** Por eso su plano tiene un workflow que el otro no tiene.

```
                              ¿QUÉ CAMBIÓ?
                                    │
        ┌───────────────────────────┴────────────────────────────┐
        ▼                                                        ▼
   ┌──────────┐                                          ┌──────────────┐
   │  LA APP  │                                          │  LA INGESTA  │
   └──────────┘                                          └──────────────┘
  apps/api · apps/bot                          pipelines/ingestion    faqs.txt
        │                                                │               │
        ▼                                                ▼               ▼
   build-app.yml                                 build-ingest.yml    subir a S3
   construye api y/o bot                         construye la imagen  + Run workflow
        │                                                │                 │
        ▼                                                ▼                 │
   ECR (api, bot)                              ECR (ingestion)              │
        │                                                │                 │
        ▼                                                └────────┬────────┘
   deploy-app.yml                                                 ▼
   pull + up -d                                             ingest.yml
   + bootstrap de la caja                          EC2 · docker run --rm
        │                                          chunking, embeddings
        ▼                                                        │
   api · bot en la                                               ▼
   versión nueva                                        vector_db → S3
                                                                 │
                                                                 ▼
                                                       deploy-db-vector.yml
                                                       fetch + up -d
                                                       --force-recreate vector-db
                                                                 │
                                                                 ▼
                                                        vector-db con el
                                                        índice nuevo

   Los tres workflows que entran al EC2 (deploy-app, ingest, deploy-db-vector)
   comparten el grupo de concurrencia "ec2": hacen fila, nunca se pisan.
   Siempre por SSM, sin SSH y sin puertos de entrada.
```


> **Por qué `--force-recreate` solo para `vector-db`.** Es el caso inverso al de api y bot, y
> por eso necesita una excepción. La imagen de Chroma (`chromadb/chroma:1.5.9`) **no cambió**:
> lo que cambió son los datos montados debajo, y eso Docker no lo mira — `up -d` lo dejaría
> intacto sirviendo el índice viejo. Encima `fetch_vector_db.sh` no rellena la carpeta del
> índice: la **intercambia** por otra con el mismo nombre, y el bind mount se resuelve una
> sola vez al arrancar, así que el contenedor sigue enganchado a la carpeta original.
> Sin recrearlo, el índice nuevo no llega nunca — y falla en silencio.

## Flujo CI/CD — casuísticas

Las cuatro situaciones que pueden pasar, paso a paso.

### 1 · Cambia código de api o bot

```
push a main 
si hubo cambios en apps/api/ o apps/bot/ (Github)
   │
   ▼ 
build-app.yml (Github Actions)
   └─ se crea las imagenes de apps/ y/o bot/
   ├─ job changes  → compara con el commit anterior
   │                 → matriz: [api], [bot] o las dos
   └─ job build    → OIDC → login en ECR
                   → docker build (contexto = raíz del repo)
                   → push con 2 tags: el SHA y latest
   │
   ▼
deploy-app.yml (Ansible)
   ├─ toma el grupo de concurrencia "ec2" (si hay algo corriendo, espera)
   ├─ acción ec2-access: OIDC · instala SSM plugin + Ansible
   │                     lee instance_id y ecr_registry del tfstate
   │                     espera a que SSM diga Online
   └─ ansible-playbook playbook.yml --tags bootstrap,app
        · instala Docker y el plugin compose si faltan
        · copia el compose y fetch_vector_db.sh, escribe .env.prod (0600)
        · login en ECR con el instance profile
        · el índice: SOLO lo baja si la carpeta no existía
        · docker compose pull   → trae el :latest nuevo
        · docker compose up -d  → el ID de imagen cambió → recrea api y/o bot
        · docker compose ps + df -h
```

**Lo que NO pasa:** `build-ingest` no arranca, la ingesta no corre, el índice no se toca.
`vector-db` sigue corriendo intacto porque su imagen (`chromadb/chroma:1.5.9`) no cambió.

---

### 2 · Cambia código de la ingesta

```
[push a main] (GitHub) 
Si hubo cambios en pipelines/ingestion/
   │
   ▼ 
[build-ingest.yml] (GitHub actions)
   └─ se crea la imagen de ingest
   │
   ▼ 
[ingest.yml] (GitHub actions & Ansible)
   ├─ Crea la BD vectorial/indice (usa ec2) y lo sube a S3 bucket
   └─ ansible-playbook ingest.yml
        · comprueba que existe /opt/anybuddy/.env.prod
          (si no, falla pidiendo deploy-app: la ingesta lo consume, no lo escribe)
        · docker pull anybuddy-ingestion:latest
        · docker run --rm --env-file .env.prod   ← SIN montar /data/chroma_storage
             baja faqs.txt y el modelo de embeddings de S3
             chunking + embeddings → arma Chroma DENTRO del contenedor
             APP_ENV=production → comprime y sube a s3://…/vector_db/
        · docker rmi   (libera varios GB de los 20 del disco)
   │
   ▼
[deploy-db-vector.yml] (Ansible)
   ├─ crea el contenedor vector-db (usa ec2)
   └─ ansible-playbook playbook.yml --tags vector-db -e refresh_index=true
        · fetch_vector_db.sh: baja el .tar.gz, extrae en .new,
          renombra la actual a .old y .new pasa a ser chroma_storage
        · docker compose up -d --force-recreate vector-db
   │
   ▼
Chroma renace apuntando a la carpeta nueva. api y bot NI SE ENTERAN.
```

Dos detalles que explican el diseño: la ingesta **no monta** la carpeta del índice a
propósito (sería escribir por debajo de Chroma mientras está sirviendo), y el
`--force-recreate` es obligatorio porque el script *intercambia* la carpeta y el bind mount
del contenedor quedó enganchado a la vieja.

**`deploy-app.yml` no corre**: escucha a `build-app`, que no arrancó.

---

### 3 · Cambia el `faqs.txt` del knowledge base

**No pasa nada de forma automática.** No hay push, no hay build, y subir un archivo a S3 no
dispara nada por sí solo.

```bash
aws s3 cp faqs.txt s3://anybuddy-artifacts/knowledge_base/faqs.txt --region us-east-2
gh workflow run ingest.yml
```

Desde ahí es **el mismo camino que la casuística 2, pero sin build**: la ingesta usa la
imagen `:latest` que ya estaba en ECR. Y al terminar, `deploy-db-vector.yml` se encadena
solo — el `workflow_run` no distingue si `ingest` arrancó a mano o automático.

Un comando, y el resto va solo.

---

### 4 · Cambian los dos a la vez, en el mismo push

Los `paths` de los dos builds matchean, así que **arrancan en paralelo**. Tienen grupos de
concurrencia distintos, no se estorban.

```
push
 ├──► build-app.yml      ~7 min (api)  ó ~1 min (bot)
 └──► build-ingest.yml   ~15 min
        │
build-app termina primero
 └──► deploy-app.yml ────► toma "ec2" ─── despliega api/bot ──┐
                                                              │
build-ingest termina                                          │
 └──► ingest.yml ──► pide "ec2" ──► ESPERA ◄──────────────────┘
                          │
                          ▼ (deploy-app soltó el grupo)
                     corre la ingesta, ~20 min
                          │
                          ▼
                  deploy-db-vector.yml ──► toma "ec2" ──► índice nuevo
```

Sale en el orden correcto —**app primero, ingesta después, índice al final**— sin haberlo
forzado: pasa solo porque el build de la app es más rápido y la fila lo respeta.

Y lo importante: si `build-ingest` o la ingesta fallan, **el deploy de api y bot ya
ocurrió**. Ese acoplamiento es justamente lo que la separación en dos planos elimina.

Lo mismo aplica si tocás `packages/model_loader/`, que está en los `paths` de los dos.