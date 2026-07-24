variable "project" {
  description = "Prefijo de nombres."
  type        = string
}

variable "ami_id" {
  description = "AMI a usar (Amazon Linux 2023)."
  type        = string
}

variable "instance_type" {
  description = "Tipo de instancia."
  type        = string
}

variable "root_volume_gb" {
  description = "Tamaño del disco raíz en GB."
  type        = number
}

variable "instance_profile" {
  description = "Nombre del instance profile IAM a adjuntar."
  type        = string
}

variable "vpc_id" {
  description = "VPC donde se crea el security group."
  type        = string
}

variable "subnet_id" {
  description = "Subnet donde se lanza la instancia."
  type        = string
}
