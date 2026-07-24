output "vpc_id" {
  description = "ID de la VPC creada."
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "ID de la subnet pública donde vive el EC2."
  value       = aws_subnet.public.id
}
