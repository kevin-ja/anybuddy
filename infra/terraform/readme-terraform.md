# Terraform

Terraform define la infraestructura de AWS como código y la crea automáticamente. Esto la hace repetible, versionable y fácil de modificar o recrear, sin configurar recursos manualmente.

la organización esta hecha en módulos, donde cada uno se encarga de una responsabilidad específica.

- Un módulo se encarga de la **red**.
- Otro se encarga de los **permisos**.
- Otro se encarga del **servidor**.
- Otro se encarga de la infra que se necesita para los **eventos**

La **raíz** (`infra/terraform/main.tf`) es el orquestrador: no crea recursos por su
cuenta, sino que **llama a los módulos**, les pasa los datos que necesitan y **conecta la
salida de uno con la entrada de otro**

## 1. Estructura de directorios

```
infra/terraform/
├── providers.tf      # con qué nube hablar y dónde guardar la "memoria" (estado)
├── variables.tf      # las "perillas" configurables (región, tamaños, CIDRs...)
├── terraform.tfvars  # los valores concretos de esas perillas
├── main.tf           # el director: consulta la AMI y llama a los 3 módulos
├── outputs.tf        # los datos que Terraform imprime al terminar (IDs, IP, ARN)
└── modules/
    ├── network/      # VPC + subnet pública + internet gateway + rutas
    ├── iam/          # rol + permisos del servidor (S3 mínimo + SSM) + instance profile
    ├── compute/      # el EC2 + su security group (solo salida, sin entrada)
    └── events/       # VACÍO por ahora (reservado para el disparador event-driven)
```

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
`instance_id` (para apuntarle con SSM), `instance_public_ip`, `vpc_id` y `instance_role_arn`.


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

Crea:
- un **rol IAM** que el EC2 puede asumir
- una **política de S3 mínima**: **leer** de `knowledge_base/`, `models/` y `vector_db/`,
  y **escribir** solo en `vector_db/` (nada más),
- el permiso **SSM** (`AmazonSSMManagedInstanceCore`) para poder administrar el EC2 sin SSH, y
- un **instance profile**, que es el envoltorio con el que ese rol se "engancha" a un EC2.

**usuario IAM creado previamente = permiso para construir (una vez); rol = permiso que usa el EC2 para funcionar.**


### 3.3. `modules/compute/` — el servidor
**Para qué sirve:** crear la máquina real que corre la ingesta y sirve los 3 contenedores.

Crea:
- **Security group** de **solo salida** (`egress`): el EC2 puede iniciar conexiones
  hacia afuera, pero **nadie puede entrar** (cero inbound; se administra por SSM, no SSH)
- **Instancia EC2** en sí (tipo `t3.small`, disco `gp3` de 20 GB), usando la AMI, la
  subnet, el instance profile y el security group que le llegan como entrada.


### 3.4. `modules/events/`

- Para que el evento pueda correr debe existir una infra subyacente.
- Es eso precisamente lo que hace Terraform: **preparar la infra**
para que, cuando el evento ocurra, encuentre los recursos necesarios para materializarse.
- Terraform arma el cableado una sola vez; la ejecución (ingesta + re-run de containers) pasa después en el EC2, y no la hace Terraform.


## 4. Cómo se conectan (el cableado entre módulos)

La magia de la modularidad es que la **salida de un módulo se enchufa en la entrada de otro**.
Terraform mira estas dependencias y **decide solo el orden** de creación (primero la red y
los permisos, después el servidor que los usa).

```
[data: AMI Amazon Linux 2023] -(ami_id)-> [módulo compute]

[módulo network] -(vpc_id, public_subnet_id)-> [módulo compute]

[módulo iam] -(instance_profile_name)-> [módulo compute]

[módulo compute] -(instance_id, public_ip)-> [outputs.tf]
[módulo network] -(vpc_id)-> [outputs.tf]
[módulo iam]     -(role_arn)-> [outputs.tf]
```

En palabras:
- El **compute** no sabe fabricar una red ni permisos: **recibe** el `vpc_id` y la subnet del
  **network**, y el `instance_profile` del **iam**, ya hechos.
- El `ami_id` viene del bloque `data` de `main.tf` (el sistema operativo más reciente).
- Al final, `outputs.tf` junta los datos clave de los tres para mostrártelos.

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

