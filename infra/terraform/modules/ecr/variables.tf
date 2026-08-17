variable "project" {
  description = "Prefijo de nombres."
  type        = string
}

variable "services" {
  description = "Servicios cuyas imágenes se publican en ECR; el repo se llama <project>-<servicio>."
  type        = list(string)
  default     = ["api", "bot", "ingestion"]
}

variable "image_retention_count" {
  description = "Cuántas imágenes recientes conservar por repo (las más viejas se expiran)."
  type        = number
  default     = 10
}
