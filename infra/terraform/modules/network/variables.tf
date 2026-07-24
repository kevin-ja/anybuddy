variable "project" {
  description = "Prefijo de nombres."
  type        = string
}

variable "vpc_cidr" {
  description = "Rango de direcciones IP privadas de la VPC."
  type        = string
}

variable "public_subnet_cidr" {
  description = "Rango de la subnet pública; debe estar contenido en vpc_cidr."
  type        = string
}
