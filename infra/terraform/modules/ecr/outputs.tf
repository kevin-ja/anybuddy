output "repository_urls" {
  description = "Mapa servicio -> URL del repo ECR (para el docker push y el compose.prod)."
  value       = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "gha_build_role_arn" {
  description = "ARN del rol que GitHub Actions asume vía OIDC para hacer push a ECR."
  value       = aws_iam_role.gha_build.arn
}
