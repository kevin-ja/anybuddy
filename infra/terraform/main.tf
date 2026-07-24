# -- CONSULTAR INFORMACIÓN A AWS (DATA) --
# Un bloque "data" NO crea recursos en la nube, sino sirve para consultar 
# un dato que ya existe en AWS o que cambia constantemente.
# Aquí le pregunta a AWS: "Oye, ¿cuál es el ID exacto del sistema operativo Amazon Linux 2023 
# más reciente hoy?". Terraform anota la respuesta y la guarda para usarla más abajo.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# -- MÓDULO DE SEGURIDAD Y PERMISOS (IAM) --
# Crea los roles, accesos y permisos de seguridad del proyecto.
# Llamamos a una carpeta ("./modules/iam") donde estos permisos ya están diseñados.
# Solo le pasamos los datos que nos pide (las variables).

module "iam" {
  source           = "./modules/iam"
  project          = var.project
  artifacts_bucket = var.artifacts_bucket
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

# -- MÓDULO DE MAQUINAS/SERVIDORES (COMPUTE) --
# Sirve para crear los servidores reales.
# Lo genial aquí es cómo se conecta con todo lo anterior usando "cables virtuales":
# 1. ami_id: Le inyecta el sistema operativo actualizado que averiguamos en el bloque "data".
# 2. instance_profile: Le entrega al servidor el "fotocheck" o gafete de seguridad que 
#    acaba de fabricar el módulo "iam" de arriba, para que el servidor tenga permisos.
module "compute" {
  source           = "./modules/compute"
  project          = var.project
  ami_id           = data.aws_ssm_parameter.al2023.value
  instance_type    = var.instance_type
  root_volume_gb   = var.root_volume_gb
  instance_profile = module.iam.instance_profile_name
  vpc_id           = module.network.vpc_id
  subnet_id        = module.network.public_subnet_id
}