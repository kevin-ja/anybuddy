resource "aws_security_group" "ec2" {
  name        = "${var.project}-ec2-sg"
  description = "Egress-only; acceso administrativo por SSM."
  vpc_id      = var.vpc_id

  egress {
    description = "Todo el trafico saliente."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "app" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  iam_instance_profile   = var.instance_profile
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.ec2.id]

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
  }

  tags = {
    Name = "${var.project}-app"
    Role = "${var.project}-app"
  }
}
