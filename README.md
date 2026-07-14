Las 3 capas, desacopladas — cada una ignora a las otras:
✅ Real:        [host EC2] baja de S3 → descomprime en /data (EBS)
                        ↓ bind mount
                [contenedor chroma] solo lee /data, agnóstico a todo


┌───────────────────────────┬───────────────────────────────────────────────────────────────────────┬───────────────────┐
│           Capa            │                               Qué hace                                │      Cuándo       │
├───────────────────────────┼───────────────────────────────────────────────────────────────────────┼───────────────────┤
│ Terraform                 │ Crea EC2 + EBS, y monta el EBS en /data                               │ Una vez           │
├───────────────────────────┼───────────────────────────────────────────────────────────────────────┼───────────────────┤
│ deploy.sh (Bash, vía SSM) │ Baja index.tar.gz de S3, lo extrae en /data/chroma, docker compose up │ Cada release      │
├───────────────────────────┼───────────────────────────────────────────────────────────────────────┼───────────────────┤
│ docker-compose            │ Monta /data/chroma en el contenedor Chroma                            │ Runtime (siempre) │
└───────────────────────────┴───────────────────────────────────────────────────────────────────────┴───────────────────┘
Las tres capas nunca se conocen entre sí:


Terraform      →  garantiza que /data (EBS) EXISTE y persiste
                            │
Deploy script  →  llena /data con el índice bajado de S3
                            │
docker-compose →  monta /data en el contenedor; Chroma lee y ya


El contenedor es agnóstico porque solo declara volumes: - /data/chroma:/chroma/chroma. Le da igual quién puso los archivos ahí, ni de dónde vinieron. Podría ser S3, un USB, o tu mano — Chroma solo ve una carpeta con su índice. Eso es el desacoplamiento que tu intuición pedía.

Rutas EBS:
- El EBS no tiene URL. Es un dispositivo (/dev/xvdf) que Terraform monta en /data.
- Desde ahí, /data/chroma es una ruta de archivos normal — solo que físicamente cae en el EBS (persiste aunque muera la instancia).

El flujo del índice:
S3 (.tar.gz) → deploy.sh baja y extrae → /data/chroma (EBS) → bind mount → contenedor Chroma

Las 2 ideas que corrigieron tu modelo:
1. El contenedor Chroma es agnóstico: no toca S3, no descarga nada, solo lee un volumen. volumes: - /data/chroma:/chroma/chroma.
2. La descarga ocurre fuera del contenedor, en el host, porrantiza que /data exista; deploy.sh lo llena.

Dónde vive cada cosa en tu repo:
- infra/docker-compose.yml — los 3 servicios (vacío hoy)
- infra/deploy/deploy.sh — el script Bash (no existe hoy)
- Terraform — capa que aún no empiezas
- .github/workflows/deploy.yml — dispara deploy.sh vía aws


# Ingestion
## Pasos a seguir
### Nivel 1 — Autenticación de GitHub hacia AWS (OIDC)
#### Parte A — Crear el identity provider (proveedor de identidad)

Esto le enseña a AWS a confiar en los tokens que emite GitHub. Se hace una sola vez por cuenta.
- La URL = confías en el país que emitió el pasaporte (verificas que el sello es auténtico).
- El Público = confirmas que la visa dentro dice específicamente "válida para entrar a AWS", no a otro lado.

1. Entra a la consola y busca IAM en la barra de búsqueda.
2. En el menú lateral: Access management (administracion del acceso) → Identity providers (proveedores de identidad).
3. Click en Add provider (agregar proveedor).
4. Provider type (tipo de proveedor): elige OpenID Connect.
5. Provider URL (URL del proveedor): escribe
https://token.actions.githubusercontent.com
y luego click en Get thumbprint (obtener huella digital). La consola la calcula sola.
6. Publico (audience): escribe sts.amazonaws.com
(STS es el Security Token Service, el servicio que emite los tokens temporales).
7. Click en Add provider.

#### Parte B — Crear el role (rol) que GitHub va a asumir

1. En IAM, ve a Roles → Create role (crear rol).
2. Trusted entity type (tipo de entidad de confianza): elige Política de confianza personalizada
3. en el json pega esto y remmplaza el "ACCOUNT_ID":

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:kevin-ja/anybuddy:*"
        }
      }
    }
  ]
}

---
Parte C — Adjuntar los permisos (permissions policy)

1. Haz click en Siguiente (Next).
2. En la pantalla de permisos, no marques nada (los agregamos después). Click en Siguiente.
3. Nombre del rol: anybuddy-gha-ingest.
4. Revisa que todo esté bien y click en Crear rol (Create role).

Agrega la inline policy (política de permisos): El rol ya existe pero no puede hacer nada todavía — no tiene permisos. Se los damos:

1. Ve a Roles, busca anybuddy-gha-ingest y haz click en su nombre.
2. En la pestaña Permisos (Permissions), busca el botón Agregar permisos (Add permissions) → Crear política insertada (Create inline policy).
3. Cambia a la pestaña JSON y pega esto (ya está listo para tu bucket anybuddy-artifacts):

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadKnowledgeAndModel",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::anybuddy-artifacts/knowledge_base/*",
        "arn:aws:s3:::anybuddy-artifacts/models/*"
      ]
    },
    {
      "Sid": "WriteVectorDb",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
      "Resource": ["arn:aws:s3:::anybuddy-artifacts/vector_db/
    }
  ]
}

4. Click en Siguiente, nómbrala ingest-s3-access, y Crear política (Create policy).

Qué hace esta policy, en corto:
- ReadKnowledgeAndModel → deja leer (s3:GetObject) el faqs.txt (knowledge_base/*) y el modelo de embedding (models/*).
- WriteVectorDb → deja escribir (s3:PutObject) el resultado .tar.gz en el prefijo approved/. (AbortMultipartUpload es por si la subida es grande y se corta a la mitad, para poder limpiar.)

---
Parte D — Copiar el ARN y guardarlo en GitHub

1. En la página de resumen del role anybuddy-gha-ingest, arriba verás el ARN (Amazon Resource Name, el identificador único del recurso). Cópialo — se ve así:
arn:aws:iam::123456789012:role/anybuddy-gha-ingest
2. Ve a tu repositorio en GitHub → Settings → Secrets and variables → Actions → pestaña Variables (variables, no secrets, porque el ARN no es información sensible) → New repository variable.
3. Nombre: AWS_ROLE_ARN. Valor: el ARN que