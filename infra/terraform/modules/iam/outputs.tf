output "instance_profile_name" {
  description = "Nombre del instance profile a adjuntar al EC2."
  value       = aws_iam_instance_profile.ec2.name
}

output "role_arn" {
  description = "ARN del rol IAM del EC2."
  value       = aws_iam_role.ec2.arn
}
