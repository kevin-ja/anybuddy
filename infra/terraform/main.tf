# -- MÓDULO DE SEGURIDAD Y PERMISOS (IAM) --
# Crea los roles, accesos y permisos de seguridad del proyecto. Son dos identidades
# distintas y conviene no confundirlas:
#   1. El rol del EC2 (instance profile): lo que la máquina puede hacer sola.
#   2. El rol "anybuddy-gha-build": lo que GitHub Actions puede hacer, asumido por
#      OIDC y sin access keys. Cubre el build (push a ECR) y el deploy (abrir sesión
#      SSM contra el EC2 para que Ansible entre por ahí, sin SSH ni puerto 22).
# El rol de GitHub vivía antes dentro de ./modules/ecr; se mudó aquí porque ya no
# es solo de ECR.
module "iam" {
  source              = "./modules/iam"
  project             = var.project
  artifacts_bucket    = var.artifacts_bucket
  github_repo         = var.github_repo
  ecr_repository_arns = module.ecr.repository_arns
  tfstate_key         = var.tfstate_key
  ssm_transfer_prefix = var.ssm_transfer_prefix
}

# Bloque MOVED: Nota de reorientación para Terraform
# CONTEXTO: se tenia una configuracion PREVIA y se movieron recursos de un módulo a otro
# Permite reorganizar el código en Terraform manteniendo ese puente de autenticación 
# intacto en AWS, garantizando despliegues continuos y sin interrupciones. De otra
# manera el flujo fallaria en algun punto, y neesitaria intervencion MANUAL para arreglarlo.
moved {
  from = module.ecr.aws_iam_openid_connect_provider.github
  to   = module.iam.aws_iam_openid_connect_provider.github
}

moved {
  from = module.ecr.aws_iam_role.gha_build
  to   = module.iam.aws_iam_role.gha_build
}

moved {
  from = module.ecr.aws_iam_role_policy.gha_build_ecr
  to   = module.iam.aws_iam_role_policy.gha_build_ecr
}

# -- MÓDULO DE RED (NETWORK) --
# Crea la red propia del proyecto en vez de usar la VPC "default" que AWS regala
# (esa se puede borrar y no siempre existe). Incluye: la VPC, una subnet pública,
# y el internet gateway con su ruta, para que el EC2 tenga salida a internet
# (bajar imágenes de ECR, hablar con S3 y con SSM).
module "network" {
  source             = "./modules/network"
  project            = var.project
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
}

# -- MÓDULO DE REGISTRO DE IMÁGENES (ECR) --
# Crea los 3 repos de ECR (api, bot, ingestion) donde GitHub Actions sube las imágenes
# ya construidas, con la política que conserva solo las 10 más recientes. Exporta los
# ARNs para que el módulo iam acote el permiso de push exactamente a estos repos.
module "ecr" {
  source  = "./modules/ecr"
  project = var.project
}

# -- MÓDULO DE MAQUINAS/SERVIDORES (COMPUTE) --
# Sirve para crear los servidores reales.
# Lo genial aquí es cómo se conecta con todo lo anterior usando "cables virtuales":
# 1. ami_id: Le inyecta el sistema operativo, fijado a mano en terraform.tfvars.
# 2. instance_profile: Le entrega al servidor el "fotocheck" o gafete de seguridad que
#    acaba de fabricar el módulo "iam" de arriba, para que el servidor tenga permisos.
module "compute" {
  source           = "./modules/compute"
  project          = var.project
  ami_id           = var.ami_id
  instance_type    = var.instance_type
  root_volume_gb   = var.root_volume_gb
  instance_profile = module.iam.instance_profile_name
  vpc_id           = module.network.vpc_id
  subnet_id        = module.network.public_subnet_id
}