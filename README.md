# anybuddy 2.0

Bot RAG para Discord. La app corre con `docker compose` (ver `infra/`).

## Infraestructura (Terraform)

La infra en AWS se declara con Terraform en `infra/terraform/`, no a mano.

> **Nota sobre la cantidad de archivos.** Terraform lee TODOS los `.tf` de una
> carpeta como si fueran uno solo; los nombres (`variables.tf`, `main.tf`, …) son
> solo para ordenar. Acá está partido en varios por convención y por usar
> "módulos". Si preferís menos archivos, todo esto cabe en 1 o 2 (ver el final).

### Qué es cada archivo, en lenguaje plano

**Archivos de la raíz (`infra/terraform/`)**

- **`providers.tf`** — Le dice a Terraform *contra qué nube* trabaja (AWS) y
  *dónde guarda su "libreta"* del estado (en el bucket S3 `anybuddy-artifacts`,
  carpeta `tfstate/`). Esa libreta es cómo Terraform recuerda qué creó.

- **`variables.tf`** — La lista de *perillas configurables* (región, tipo de EC2,
  tamaño de disco, nombre del bucket). Solo declara que existen y su valor por
  defecto; no pone los valores finales.

- **`terraform.tfvars`** — Los *valores concretos* de esas perillas. Es el único
  archivo que tocás para cambiar región, tamaño, etc.

- **`main.tf`** — El *cableado*: busca la imagen del sistema (Amazon Linux 2023) y
  arma la infra llamando a los módulos (abajo). Es el "índice" del conjunto.

- **`outputs.tf`** — Lo que Terraform te *imprime al terminar* (ID del EC2, su IP,
  el ID de la VPC y el ARN del rol). Datos que después necesitás para el disparador
  event-driven (módulo `events`, más adelante).

**Módulos (`infra/terraform/modules/`)** — cajitas reutilizables. Cada una trae 3
archivos: `main.tf` (los recursos), `variables.tf` (lo que recibe) y `outputs.tf`
(lo que devuelve).

- **`modules/network/`** — La *red propia*. Crea una **VPC** (`10.0.0.0/16`) con
  una **subred pública** (`10.0.1.0/24`), un **internet gateway** y su tabla de
  rutas. No se usa la VPC "default" de AWS (se puede borrar y no siempre existe).
  La subred es pública porque el EC2 necesita salida a internet (ECR, S3, SSM) y
  aun así no abre ningún puerto de entrada.

- **`modules/iam/`** — Los *permisos*. Crea el "rol" (instance profile) que usa el
  EC2 para poder: leer los artefactos de S3 (`knowledge_base/`, `models/`),
  escribir el índice (`vector_db/`) y ser administrado por **SSM** (ejecutar
  comandos sin abrir SSH). Con esto el EC2 no necesita access keys en disco.

- **`modules/compute/`** — La *máquina*. Crea el **EC2** (`t3.small`, donde correrá
  la ingesta efímera y el `docker compose`) con disco `gp3` de 20 GB, dentro de la
  subred del módulo `network`, y un **security group** que solo deja salir tráfico
  (no abre ningún puerto de entrada; se entra por SSM).

- **`modules/events/`** — *Vacío por ahora* (solo un README). Reservado para el
  disparador event-driven (EventBridge → SSM; Lambda solo si hace falta lógica)
  que detecta cambios de artefacto en S3 y ordena la re-ejecución en el EC2.

### Qué crea hoy (Fase 0), en una frase

Una red propia (VPC + subred pública + IGW) con un servidor (EC2) que tiene los
permisos justos para leer/escribir en S3 y ser operado remotamente por SSM. Nada
más. La automatización event-driven (módulo `events`) viene después.

### Credenciales — el usuario IAM de Terraform (requisito previo)

Terraform necesita un **usuario IAM** propio (no un rol: los roles no tienen access
keys, y Terraform se autentica con las 2 llaves). Se crea **una sola vez** en la
cuenta `176285591978`, distinto del `anybuddy-ingestion` (que solo tiene S3).

- **Qué crear:** un usuario IAM (ej. `anybuddy-terraform`) con **access key**
  (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`).
- **Qué permisos necesita** (porque va a crear red + EC2 + el rol del EC2):

  | Área | Para qué |
  |---|---|
  | **EC2 / VPC** | crear VPC, subred, internet gateway, route table, security group, la instancia EC2 y sus tags |
  | **SSM (lectura)** | `ssm:GetParameter` sobre los parámetros públicos `/aws/service/*` para resolver la AMI de Amazon Linux 2023 |
  | **IAM** | crear el **rol + instance profile** del EC2 (`CreateRole`, `AttachRolePolicy`, `CreateInstanceProfile`, `PassRole`) |
  | **S3** | leer/escribir el **tfstate** en `anybuddy-artifacts/tfstate/*` |

- **Cómo se entregan las llaves:** por variables de entorno (`export
  AWS_ACCESS_KEY_ID=…` / `AWS_SECRET_ACCESS_KEY=…`), **no** en `~/.aws/credentials`.
  Mismo mecanismo en local y en CI (GitHub secrets), sin secretos en disco.

**Política mínima (recomendada, no `PowerUserAccess`).** `PowerUserAccess` abre casi
todos los servicios de AWS (SageMaker, Athena, Bedrock, RDS…); es de más. Se le
adjunta al usuario una **inline policy** acotada a solo lo que Terraform toca:
`ec2:*` (que incluye VPC/subred/IGW/route-table/SG/instancia), `ssm:GetParameter`
solo sobre los parámetros públicos de AWS (`/aws/service/*`, para resolver la AMI),
S3 solo sobre el bucket `anybuddy-artifacts`, e IAM solo sobre roles/instance-profiles
`anybuddy-*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RedesYEC2",
      "Effect": "Allow",
      "Action": "ec2:*",
      "Resource": "*"
    },
    {
      "Sid": "LeerAMIviaSSM",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:*::parameter/aws/service/*"
    },
    {
      "Sid": "TfstateYArtefactosS3",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::anybuddy-artifacts",
        "arn:aws:s3:::anybuddy-artifacts/*"
      ]
    },
    {
      "Sid": "RolInstanceProfileDelEC2",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:TagRole",
        "iam:PassRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:CreateInstanceProfile",
        "iam:DeleteInstanceProfile",
        "iam:GetInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:RemoveRoleFromInstanceProfile"
      ],
      "Resource": [
        "arn:aws:iam::176285591978:role/anybuddy-*",
        "arn:aws:iam::176285591978:instance-profile/anybuddy-*"
      ]
    }
  ]
}
```

> `ec2:*` es **un solo servicio** (VPC y compañía viven en ese namespace), no "todos
> los servicios". Si en el futuro los recursos IAM del proyecto no siguen el prefijo
> `anybuddy-*`, ajustá el `Resource` de la última sentencia.

> No usar el perfil `default` del CLI: apunta a otra cuenta (`816069170567`).
> Verificar con `aws sts get-caller-identity` que responde la cuenta `176285591978`.

<details>
<summary><b>Cómo se creó, en 5 pasos (consola IAM)</b></summary>

1. **Políticas → Create policy →** pestaña JSON → pegar el JSON de arriba →
   nombrarla `terraform-policy`.
2. **Users → Create user →** nombre `anybuddy-terraform` (sin acceso a consola).
3. En permisos: **Attach policies directly →** buscar y marcar `terraform-policy`
   → **Create user**.
4. Entrar al usuario → **Security credentials → Create access key →** caso de uso
   **CLI**.
5. **Copiar las 2 llaves** en el momento (el *secret* no se vuelve a mostrar) y
   exportarlas como variables de entorno.

</details>

### Cargar las credenciales en la terminal

Las llaves viven en `.env.aws` (en la raíz del repo, ignorado por git y docker). Para
que Terraform/AWS CLI las hereden, hay que **exportarlas** en la sesión:

```bash
# parado en la raíz del repo
set -a; source .env.aws; set +a
aws sts get-caller-identity   # verificá: cuenta 176285591978
```

- **`set -a`** enciende el modo "exportar todo": lo que se cargue queda disponible para
  los procesos hijos (Terraform, AWS CLI).
- **`source .env.aws`** lee el archivo con las llaves (con el modo encendido → se exportan).
- **`set +a`** apaga el modo (higiene: no exporta variables futuras sin querer).

> Hay que repetirlo en cada terminal nueva. Sin `set -a`, las variables quedan locales y
> Terraform **no las ve**.

### Uso

```bash
cd infra/terraform
terraform init      # descarga el provider de AWS y conecta la libreta (S3)
terraform plan      # muestra qué va a crear, sin crear nada
terraform apply     # crea la infra de verdad
```

> Requisito: el bucket `anybuddy-artifacts` debe existir (ya está) y tener
> exportadas las credenciales del usuario IAM de arriba en tu entorno.

### ¿Y si quiero MENOS archivos?

Todo lo de arriba se puede aplastar a **un solo `main.tf`** (o `main.tf` +
`variables.tf`) sin módulos. Se pierde la reutilización, pero para 1 servidor es
más que suficiente y se lee de un vistazo. Los módulos valen la pena solo cuando
repetís la misma pieza o el archivo único se vuelve enorme.
