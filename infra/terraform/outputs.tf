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
