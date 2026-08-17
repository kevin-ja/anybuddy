output "repository_urls" {
  description = "Mapa servicio -> URL del repo ECR (para el docker push y el compose.prod)."
  value       = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "repository_arns" {
  description = "ARNs de los repos, para que el módulo iam acote el permiso de push a estos y no a todo ECR."
  value       = [for r in aws_ecr_repository.this : r.arn]
}
