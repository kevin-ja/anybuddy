output "instance_id" {
  description = "ID del EC2 (úsalo como target de SSM RunCommand)."
  value       = module.compute.instance_id
}

output "instance_public_ip" {
  description = "IP pública del EC2 (null si no tiene)."
  value       = module.compute.public_ip
}

output "vpc_id" {
  description = "ID de la VPC del proyecto."
  value       = module.network.vpc_id
}

output "instance_role_arn" {
  description = "ARN del rol IAM que asume el EC2."
  value       = module.iam.role_arn
}

output "ecr_repository_urls" {
  description = "URLs de los repos ECR (para el docker push y el compose.prod)."
  value       = module.ecr.repository_urls
}

output "gha_build_role_arn" {
  description = "ARN del rol que GitHub Actions asume vía OIDC (va en la variable AWS_ROLE_ARN del repo)."
  value       = module.ecr.gha_build_role_arn
}
