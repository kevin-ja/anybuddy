output "instance_id" {
  description = "ID del EC2."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "IP pública del EC2 (null si no tiene)."
  value       = aws_instance.app.public_ip
}
