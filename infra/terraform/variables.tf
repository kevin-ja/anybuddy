variable "aws_region" {
  description = "Región AWS donde vive todo."
  type        = string
  default     = "us-east-2"
}

variable "project" {
  description = "Nombre del proyecto; se usa como prefijo y tag."
  type        = string
  default     = "anybuddy"
}

variable "artifacts_bucket" {
  description = "Bucket S3 con los artefactos (knowledge_base/, models/) y el output (vector_db/)."
  type        = string
  default     = "anybuddy-artifacts"
}

variable "github_repo" {
  description = "owner/repo de GitHub autorizado a asumir el rol de build vía OIDC."
  type        = string
  default     = "kevin-ja/anybuddy"
}

variable "tfstate_key" {
  description = "Key del tfstate dentro de artifacts_bucket. TIENE que coincidir con el backend de providers.tf: el backend no admite variables, así que este valor se repite a mano. Lo usa el rol de GitHub Actions para leer los outputs (instance_id, URL de ECR) en vez de guardarlos como secrets."
  type        = string
  default     = "tfstate/anybuddy.tfstate"
}

variable "ssm_transfer_prefix" {
  description = "Prefijo S3 que el conector aws_ssm de Ansible usa de buzón para copiar ficheros al EC2. La sesión SSM es una terminal, no un canal de archivos: Ansible sube el fichero a S3 y la instancia lo baja."
  type        = string
  default     = "ansible-ssm"
}

variable "vpc_cidr" {
  description = "Rango de direcciones IP privadas de la VPC del proyecto."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Rango de la subnet pública donde vive el EC2."
  type        = string
  default     = "10.0.1.0/24"
}

variable "ami_id" {
  description = "AMI de Amazon Linux 2023, fijada a mano. Si se pidiera la mas reciente, cambiaria sola cada vez que Amazon publica una imagen y eso reemplazaria el EC2 (y su IP publica) sin que nadie lo decida. Para ver si hay una nueva: aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --region us-east-2 --query Parameter.Value --output text"
  type        = string
}

variable "instance_type" {
  description = "Tipo de EC2 que corre ingesta + servicios (compose)."
  type        = string
  default     = "t3.small"
}

variable "root_volume_gb" {
  description = "Tamaño del disco raíz del EC2 (aloja la vector DB extraída + imágenes docker)."
  type        = number
  default     = 20
}
