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
