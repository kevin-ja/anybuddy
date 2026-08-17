# Terraform

Terraform define la infraestructura de AWS como código y la crea automáticamente. Esto la hace repetible, versionable y fácil de modificar o recrear, sin configurar recursos manualmente.

la organización esta hecha en módulos, donde cada uno se encarga de una responsabilidad específica.

- Un módulo se encarga de la **red**.
- Otro se encarga de los **permisos** (los del servidor y los de GitHub Actions).
- Otro se encarga del **servidor**.
- Otro se encarga del **registro de imágenes** (los 3 repos de ECR).
- Otro se encarga de la infra que se necesita para los **eventos**

La **raíz** (`infra/terraform/main.tf`) es el orquestrador: no crea recursos por su
cuenta, sino que **llama a los módulos**, les pasa los datos que necesitan y **conecta la
salida de uno con la entrada de otro**

## ¿En qué etapa del CI/CD participa Terraform?

- En este proyecto: En Ambos. 
- Normalmente: En ambos, aunque con una inclinacion hacia CD.

Terraform nunca ejecuta procesos, sino que provisiona la infra para que el
proceso de CI y el de CD corran sin problemas

- **En CI participa en** los 3 repos de ECR y el rol OIDC `anybuddy-gha-build`, que usan
  `build-app.yml` y `build-ingest.yml`.
- **En CD participa en** la VPC, el EC2, y los **permisos** que le abren la puerta a Ansible
  (la sesión SSM) — pero no en el deploy en sí, que hacen `deploy-app.yml`,
  `deploy-db-vector.yml` e `ingest.yml`.

**Terraform entrega la caja pelada y ahí termina.** Instalar Docker, bajar las imágenes y
levantar la app es trabajo de **Ansible**. Por
eso Terraform no hace ninguna de estas cuatro cosas: `docker build`, el `push` de las
imágenes, el `pull` en el servidor, ni el `docker compose up`.

Esa frontera se cruzó dos veces y conviene tenerla clara: hubo un diseño con `user_data`
(bootstrap dentro de Terraform) y otro con CodeDeploy. Los dos quedaron atrás. Hoy la regla
es: **Terraform declara recursos de AWS; el shell vive en `infra/ansible/`.**

| Pieza | La **crea** (una vez) | La **usa** (cada vez) |
|---|---|---|
| Repos ECR | Terraform | GitHub Actions (`push`) · EC2 (`pull`) |
| Las imágenes | — | GitHub Actions (`build-app.yml`, `build-ingest.yml`) |
| Permiso de abrir sesión SSM | Terraform (la política del rol) | Ansible, desde el runner |
| Docker + los contenedores | — | Ansible (`playbook.yml`, con tags) |
| El índice de Chroma | — | la ingesta (`ingest.yml`) lo produce; `deploy-db-vector.yml` lo instala |

## 1. Estructura de directorios

```
infra/terraform/
├── providers.tf      # con qué nube hablar y dónde guardar la "memoria" (estado)
├── variables.tf      # las "perillas" configurables (región, tamaños, CIDRs...)
├── terraform.tfvars  # los valores concretos de esas perillas
├── main.tf           # el director: consulta la AMI y llama a los módulos
├── outputs.tf        # los datos que Terraform imprime al terminar (IDs, IP, ARN, repos ECR)
└── modules/
    ├── network/      # VPC + subnet pública + internet gateway + rutas
    ├── iam/          # LAS DOS identidades: rol del EC2 (+instance profile) y rol de GitHub
    ├── compute/      # el EC2 + su security group (solo salida, sin entrada)
    └── ecr/          # 3 repos de imágenes, nada más
```

Ni `modules/deploy/` ni `modules/events/`, que figuraron acá en su momento, van a existir:
ni el deploy ni la ingesta se declaran en Terraform. Los dos son workflows.

---

## 2. El "director de orquesta": main.tf

### `providers.tf`

Configura el provider de AWS (región y autenticación mediante variables de entorno) y el backend S3, donde Terraform guarda el estado de la infraestructura para saber qué recursos ya existen y evitar duplicarlos.

### `variables.tf` + `terraform.tfvars`
variables.tf define las variables configurables (región, tipo de EC2, red, disco, etc.), mientras que terraform.tfvars les asigna los valores concretos que Terraform utilizará al desplegar la infraestructura.

### `main.tf`
Primero consulta información existente en AWS (como la última imagen de Amazon Linux 2023) y luego coordina los módulos, pasándoles la información que necesitan para trabajar juntos (por ejemplo, la red creada por un módulo es utilizada por el servidor creado por otro)

### `outputs.tf`
Cuando Terraform termina, imprime datos útiles para los siguientes pasos:
`instance_id` (a quién le habla Ansible por SSM), `instance_public_ip`, `vpc_id`,
`instance_role_arn`, `ecr_repository_urls` (las URLs de los 3 repos, para el `docker push` y
el `compose.prod`) y `gha_build_role_arn` (el ARN que va en la variable `AWS_ROLE_ARN` del
repo de GitHub).

**Estos outputs no son decorativos: son la fuente de verdad del workflow de deploy.** En vez
de copiar el `instance_id` y la URL de ECR a GitHub Secrets a mano, los workflows los leen con
`terraform output` desde el tfstate. Si mañana se recrea la EC2, el ID nuevo se propaga solo;
con secrets habría que acordarse de ir a editarlos.

Ojo con dónde quedan: Terraform los **imprime**, no los exporta. No se meten en el entorno de
tu terminal ni los hereda ningún proceso; lo único persistente es el tfstate en S3. Se leen
cuando haga falta con `terraform output -raw <nombre>` (o `-json` para el mapa de ECR).


## 3. Módulos

 ### 3.1. `modules/network/`
**Para qué sirve:** Le da al servidor una red donde vivir, con **salida a internet**.

Crea una **VPC** propia (`10.0.0.0/16`) en vez de usar la VPC "default" de AWS (esa se
puede borrar y no siempre existe → el despliegue reventaría). 

Dentro pone:
- una **subnet pública** (`10.0.1.0/24`),
- un **internet gateway** (la puerta a internet) y
- una **route table** que manda todo el tráfico saliente por esa puerta.

Es subnet **pública** porque el EC2 necesita salir a internet para bajar imágenes de ECR,
hablar con S3 y con SSM. No abre nada de entrada, así que el riesgo es bajo.


### 3.2. `modules/iam/` 

- **Tu usuario `anybuddy-terraform`** es *quién construye*. 
- Terraform lo usa **una sola vez** (`terraform apply`) para **crear** el **Rol IAM** y
sus permisos y pasarselas al EC2. 
- Por lo tanto no es un intermediario permanente: después no vuelve a intervenir (salvo que cambies la infra y
corras otro `terraform apply`). De ahí en adelante es **el EC2 mismo** quien usa
esos permisos para hablar con S3/SSM, solo.

Este módulo crea **dos identidades distintas**. Confundirlas es el error clásico, así que
van separadas:

**A) El rol del EC2** — lo que la máquina puede hacer sola:
- un **rol IAM** que el EC2 puede asumir
- una **política de S3 mínima**: **leer** de `knowledge_base/`, `models/` y `vector_db/`,
  y **escribir** solo en `vector_db/` (nada más),
- **read/write en `ansible-ssm/`**: el buzón por el que Ansible le pasa ficheros (ver abajo),
- el permiso **SSM** (`AmazonSSMManagedInstanceCore`) para poder administrar el EC2 sin SSH, y
- un **instance profile**, que es el envoltorio con el que ese rol se "engancha" a un EC2.

**B) El rol `anybuddy-gha-build`** — lo que GitHub Actions puede hacer. Lo asume el runner por
**federación OIDC** (token temporal, cero access keys guardadas en GitHub), y su *trust policy*
está limitada a tu repo (`repo:kevin-ja/anybuddy:*`). Lleva dos políticas:
- `anybuddy-gha-build-ecr` — **push a los 3 repos** y nada más. Los ARN llegan del módulo `ecr`.
- `anybuddy-gha-deploy` — lo que Ansible necesita para entrar:
  - `s3:GetObject` sobre el **tfstate**, para leer los outputs;
  - `ssm:StartSession` **acotado por tag** (`Role = anybuddy-app`) más los documentos
    `AWS-StartSSHSession` y `SSM-SessionManagerRunShell`;
  - `ssm:TerminateSession` / `ResumeSession` / `DescribeInstanceInformation`;
  - read/write en el prefijo `ansible-ssm/` de S3.

> **Por qué el `StartSession` va por tag y no por el ARN de la instancia.** Sería más preciso
> apuntar al ARN, pero no se puede: `compute` ya depende de `iam` para el instance profile, así
> que referenciar la instancia desde `iam` cerraría un ciclo. El tag `Role = anybuddy-app` que
> pone `modules/compute/` resuelve lo mismo sin ciclo.

> **Por qué hace falta un prefijo de S3 para "copiar un archivo".** Una sesión SSM es una
> terminal, no un canal de ficheros. El conector `aws_ssm` de Ansible sube cada archivo a S3 y
> hace que la instancia lo baje desde ahí. Por eso el permiso está **en las dos identidades**:
> el runner escribe, la caja lee.

**usuario IAM creado previamente = permiso para construir (una vez); rol = permiso que usa el EC2 para funcionar.**

> **Este rol vivía en `modules/ecr/`** hasta el 2026-08-07. Se mudó acá cuando dejó de ser solo
> de ECR (ahora también abre sesiones SSM y lee el tfstate). El traslado se hizo con bloques
> `moved` en `main.tf`, que le dicen a Terraform "es el mismo recurso en otra dirección" — sin
> ellos lo habría destruido y recreado, y en ese hueco los builds se quedan sin autenticarse.
> El nombre y el ARN no cambiaron: `AWS_ROLE_ARN` en GitHub sigue igual.


### 3.3. `modules/compute/` — el servidor
**Para qué sirve:** crear la máquina real que corre la ingesta y sirve los 3 contenedores.

Crea:
- **Security group** de **solo salida** (`egress`): el EC2 puede iniciar conexiones
  hacia afuera, pero **nadie puede entrar** (cero inbound; se administra por SSM, no SSH)
- **Instancia EC2** en sí (tipo `t3.small`, disco `gp3` de 20 GB), usando la AMI, la
  subnet, el instance profile y el security group que le llegan como entrada.


### 3.4. `modules/ecr/` — registro de imágenes

**Para qué sirve:** guardar las imágenes Docker ya construidas.

El build de las imágenes ocurre en un runner efímero de GitHub (nunca en el EC2); este
módulo prepara *dónde* se guardan. El *quién* tiene permiso de subirlas vive ahora en
`modules/iam/`.

Los 3 repos los llenan **dos workflows distintos**: `build-app.yml` publica `anybuddy-api` y
`anybuddy-bot`, y `build-ingest.yml` publica `anybuddy-ingestion`. Para Terraform da igual —
los tres repos son idénticos y el permiso de push es el mismo—, pero explica por qué el rol
`anybuddy-gha-build` lo asumen dos workflows y no uno.

Crea:
- **3 repos ECR** (`anybuddy-api`, `anybuddy-bot`, `anybuddy-ingestion`) con *scan on push*
  y una **lifecycle policy** que conserva solo las **10 imágenes más recientes** por repo
  (para que ECR no acumule storage sin límite).

Exporta `repository_urls` (para el `docker push` y el `compose.prod`) y `repository_arns`,
que es lo que le permite a `iam` acotar el permiso de push **exactamente a estos 3 repos** en
vez de a todo ECR.

> **Por qué el rol de GitHub ya no está acá.** Estuvo, y por una buena razón: el módulo era
> autocontenido, el rol referenciaba los repos vecinos sin cables entre módulos. Dejó de
> tenerla cuando ese mismo rol pasó a abrir sesiones SSM y leer el tfstate — cosas que no
> tienen nada que ver con un registro de imágenes. Se prefirió un cable
> (`ecr.repository_arns → iam`) antes que un módulo que miente sobre lo que contiene.

> Requiere que `terraform-policy` (del usuario `anybuddy-terraform`) tenga permisos de
> `ecr:*` acotado y de OIDC provider. Ver `README.md` (sección "Credenciales").


### 3.5. Los módulos `events/` y `deploy/` — CANCELADOS, no se van a crear

`modules/deploy/` iba a alojar un documento SSM con `docker compose pull` + `up -d`, y
`modules/events/` el disparador automático de la ingesta. Ninguno de los dos va.

El motivo es el mismo en los dos casos: **eso no es infraestructura**. El deploy lo hace
Ansible desde GitHub Actions (`deploy-app.yml` y `deploy-db-vector.yml`), y la ingesta
también (`ingest.yml`). Un playbook y un workflow no son recursos de AWS, así que no se
declaran en Terraform.

`modules/events/` además perdió su razón de ser por otro lado: la ingesta ya no se dispara
con un evento de S3. Cuando cambia el código la encadena `build-ingest.yml`, y cuando cambia
el `faqs.txt` la lanza una persona.

Lo que Terraform sí aporta a esos flujos son los **permisos** (`modules/iam/`) y los
**outputs** que los workflows leen para saber contra qué instancia hablar.


## 4. Cómo se conectan (el cableado entre módulos)

La magia de la modularidad es que la **salida de un módulo se enchufa en la entrada de otro**.
Terraform mira estas dependencias y **decide solo el orden** de creación (primero la red y
los permisos, después el servidor que los usa).

```
[var.ami_id (fijado a mano en tfvars)] -(ami_id)-> [módulo compute]

[módulo ecr]     -(repository_arns)-> [módulo iam]

[módulo network] -(vpc_id, public_subnet_id)-> [módulo compute]

[módulo iam]     -(instance_profile_name)-> [módulo compute]

[módulo compute] -(instance_id, public_ip)-> [outputs.tf]
[módulo network] -(vpc_id)-> [outputs.tf]
[módulo iam]     -(role_arn, gha_build_role_arn)-> [outputs.tf]
[módulo ecr]     -(repository_urls)-> [outputs.tf]
```

En palabras:
- El **compute** no sabe fabricar una red ni permisos: **recibe** el `vpc_id` y la subnet del
  **network**, y el `instance_profile` del **iam**, ya hechos.
- El `ami_id` **no** se averigua solo: viene fijado a mano en `terraform.tfvars`. Si se pidiera
  "el más reciente", Amazon publica una imagen nueva y el siguiente `apply` recrearía la EC2
  (y su IP) sin que nadie lo decidiera. Ya pasó una vez — está en `handsoff.md`.
- El **ecr** no recibe nada de nadie; le pasa los ARN de los repos al **iam** para que acote
  el permiso de push.
- El orden que Terraform deduce solo: `ecr` → `iam` → `compute`. No hay ciclo, y por eso el
  permiso de `StartSession` se acota **por tag** y no por el ARN de la instancia (si `iam`
  mirara a `compute`, que ya mira a `iam`, se cerraría el círculo).
- Al final, `outputs.tf` junta los datos clave de todos para mostrártelos.

---

## 6. Cómo se usa (el ciclo típico)

Desde `infra/terraform/`, con las credenciales cargadas en el entorno
(`set -a; source ../../.env.aws; set +a`):

```
terraform init      # baja el provider AWS y conecta el estado en S3 (una vez)
terraform plan      # muestra qué va a crear/cambiar SIN tocar nada
terraform apply     # crea de verdad la infra (pide confirmar con "yes")
terraform destroy   # borra todo lo que creó (cuando ya no lo necesites)
```

`plan` es tu red de seguridad: siempre lo mirás antes de `apply`. El estado remoto (en S3)
es lo que le permite a Terraform saber qué ya existe entre una corrida y la siguiente.

