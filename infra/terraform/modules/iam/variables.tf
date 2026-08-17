variable "project" {
  description = "Prefijo de nombres."
  type        = string
}

variable "artifacts_bucket" {
  description = "Bucket S3 de artefactos."
  type        = string
}

variable "github_repo" {
  description = "owner/repo autorizado a asumir el rol de CI/CD vía OIDC (ej. kevin-ja/anybuddy)."
  type        = string
}

variable "ecr_repository_arns" {
  description = "ARNs de los repos ECR a los que el runner puede hacer push."
  type        = list(string)
}

variable "tfstate_key" {
  description = "Key del tfstate dentro del bucket de artefactos. El workflow de deploy lo lee para sacar el instance_id y la URL de ECR, en vez de guardarlos como secrets."
  type        = string
}

variable "ssm_transfer_prefix" {
  description = "Prefijo S3 que el conector aws_ssm de Ansible usa como buzón para pasar ficheros entre el runner y el EC2. Ansible sube ahí y la instancia descarga. Lo impone el conector (<instance_id>/<ruta_remota>), no se configura."
  type        = string
}
