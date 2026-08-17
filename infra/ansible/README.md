# infra/ansible — el deployment

## Que hay aca

| Archivo | Que es |
|---|---|
| `playbook.yml` | Los DOS deploys, separados por tags de Ansible. Idempotente: la primera corrida hace de bootstrap, las siguientes traen de ECR la imagen publicada y recrean los contenedores si cambio. |
| `ingest.yml` | La ingesta. Corre la imagen `anybuddy-ingestion` en la caja (`docker run --rm`), que vectoriza el knowledge base y publica el indice en S3. Lo llama el workflow `.github/workflows/ingest.yml`. |
| `inventory.yml` | El inventario. Una sola caja, alcanzada por SSM (no por SSH). |
| `group_vars/all.yml` | Config no secreta, versionada. |
| `ansible.cfg` | Config de Ansible. Solo se lee si se invoca desde este directorio. |
| `templates/docker-compose.prod.yml` | El compose que corre en el EC2, en `/opt/anybuddy/`. Esta en `templates/` porque el mount de Chroma sale de `chroma_data_path`; sin extension `.j2` para que el editor lo siga coloreando como YAML (Ansible no la exige). |
| `files/fetch_vector_db.sh` | Baja el indice de Chroma desde S3 y lo extrae en la EBS |

### La ruta del indice se escribe en UN solo lugar

`chroma_data_path` (en `group_vars/all.yml`) es el dueño del valor. De ahi lo heredan
los tres que lo necesitan: la tarea que crea la carpeta, el `export` con el que se
invoca `fetch_vector_db.sh` y el mount del compose. Antes estaba escrito a mano en los
tres, y desalinearlos no rompia nada de forma visible: el script llenaba una carpeta,
Chroma montaba otra y seguia sirviendo el indice viejo con el job en verde.

## Un playbook, dos deploys

`playbook.yml` lo invocan dos workflows distintos, cada uno con sus etiquetas:

| Invocacion | Quien la usa | Que corre |
|---|---|---|
| `--tags bootstrap,app` | `deploy-app.yml` | Prepara la caja (Docker, `/opt/anybuddy`, `.env.prod`, login en ECR) y levanta los contenedores con las imagenes nuevas. |
| `--tags vector-db` + `-e refresh_index=true` | `deploy-db-vector.yml` | Baja el indice de S3 y recrea **solo** `vector-db`. No toca api ni bot. |
| sin `--tags` | a mano | Todo junto. |

Las tareas con tag `always` corren siempre: las comprobaciones de entrada y el
reporte final (`docker compose ps` + `df -h`).

Se hizo con tags y no con dos playbooks separados para no duplicar el bloque de
bootstrap ni el de checking, que son identicos en los dos casos.

**El orden importa:** `deploy-app.yml` tiene que correr primero en una caja nueva,
porque es el unico que hace el bootstrap. Si `deploy-db-vector.yml` o la ingesta
llegan antes, fallan con un mensaje claro pidiendo que se corra el deploy de la app.

## No hay bootstrap aparte

Antes esto iban a ser dos cosas: un `user_data` que preparaba la caja y un deploy
que cambiaba las imagenes. Con un playbook idempotente es una sola: si el EC2 se
recrea, la misma corrida lo vuelve a dejar sirviendo. Por eso el playbook instala
Docker aunque ya este instalado — comprueba y sigue.

## Como se conecta: SSM, no SSH

El security group del EC2 es egress-only, sin ningun ingress. No hay puerto 22
abierto ni clave `.pem` que guardar: el runner de GitHub Actions asume un rol por
OIDC y abre una sesion de SSM.

Un detalle que no es obvio: la sesion SSM es una **terminal**, no un canal de
ficheros — no hay `scp`. Para copiar un archivo, el conector lo sube al prefijo
`ansible-ssm/` del bucket de artefactos y hace que la instancia lo baje. De ahi
que el permiso este duplicado en las dos identidades (el runner escribe, la caja
lee), en `infra/terraform/modules/iam/main.tf`.

Otro: el permiso de `ssm:StartSession` esta acotado **por tag**, no por el ARN de
la instancia (habria cerrado un ciclo entre los modulos `iam` y `compute`). El tag
`Role = anybuddy-app` que pone `modules/compute/main.tf` es funcional, no
decorativo: **si se cambia, el deploy se queda sin permiso**.

## Los secretos

El `.env.prod` completo se guarda como secret `ENV_PROD` del repo, y el playbook
lo lee de la variable de entorno del mismo nombre. Se pasa por entorno y no por
`-e` porque los extra-vars quedan visibles en la lista de procesos del runner.

En la caja queda en `/opt/anybuddy/.env.prod` con permisos `0600`.

Su contenido es el de `.env.prod.example` de la raiz del repo, **menos**
`AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`: en AWS las credenciales salen del
instance profile del EC2, no de variables de entorno. Y `CHROMA_HOST` es
`vector-db` (el nombre del servicio de compose), no `localhost`.

## Correrlo a mano

Requiere `session-manager-plugin` instalado y credenciales de AWS cargadas.

```bash
pip install ansible boto3
ansible-galaxy collection install amazon.aws

cd infra/ansible
export ENV_PROD="$(cat /ruta/a/tu/.env.prod)"

ansible-playbook playbook.yml \
  -e instance_id=$(terraform -chdir=../terraform output -raw instance_id) \
  -e ecr_registry=176285591978.dkr.ecr.us-east-2.amazonaws.com
```

`instance_id` y `ecr_registry` salen de `terraform output`, no de secrets: una
sola fuente de verdad. Si se recrea el EC2, el id nuevo se propaga solo.

## El indice de Chroma

Por defecto **no** se vuelve a bajar en cada deploy: desplegar codigo nuevo no
cambia el indice, y bajarlo obligaria a reiniciar la base de datos sin motivo.
Solo se baja en la primera corrida, cuando la caja todavia no lo tiene.

Para forzarlo:

```bash
ansible-playbook playbook.yml --tags vector-db -e refresh_index=true ...
```

Es exactamente lo que hace `deploy-db-vector.yml`, que arranca solo cuando la ingesta
termina bien. Sin ese `-e`, la ingesta sube el indice a S3 y la caja sigue con el viejo.

El `-e` cambia ademas como se trata un fallo al bajar el indice: con `refresh_index=true`
un error pinta rojo, porque bajar el indice ES el motivo de la corrida. En el bootstrap de
una caja virgen se tolera, porque puede que la ingesta no haya corrido nunca todavia.

Cuando el indice cambia, el playbook recrea el contenedor `vector-db` con
`--force-recreate`. **No es opcional**: `fetch_vector_db.sh` no rellena la carpeta
del indice, la intercambia por otra con el mismo nombre, y el bind mount del
contenedor quedo enganchado a la carpeta vieja. Sin el `--force-recreate`, el host
ve el indice nuevo y Chroma sigue sirviendo el viejo, sin avisar.
