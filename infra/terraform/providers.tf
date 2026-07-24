# -- QUE VERSION USAR --
# Para correr este script necesitas tener instalado Terraform versión 1.6 o 
# superior, y necesitas bajarte el 'traductor' oficial de AWS (versión 5.x)
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # -- DONDE GUARDAR LA MEMORIA --
  # No guardes la MEMORIA en mi disco duro. Súbela a internet, específicamente a
  # este baúl (bucket S3) de AWS llamado anybuddy-artifacts.

  # MEMORIA = Es la "memoria" de Terraform. Cuando creas el servidor, Terraform 
  # genera un archivo oculto donde anota exactamente qué creó y cómo se llama en 
  # la vida real. Así, si mañana cambias el código para añadir un segundo servidor, 
  # Terraform mira su "memoria", se da cuenta de que el primero ya existe y 
  # solo crea el segundo, en lugar de duplicarlo todo
  backend "s3" {
    bucket = "anybuddy-artifacts"
    key    = "tfstate/anybuddy.tfstate"
    region = "us-east-2"
  }
}

# -- QUE PROVIDER USAR --
# PROVIDER = servicio cloud que se utilizará
# -- CON QUE CUENTA CONECTARSE --
# Las credenciales NO se escriben aca ni se leen de ningun archivo local.
# Terraform las toma solo de estas variables de entorno:
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# Es el mismo mecanismo en local y en CI (GitHub Actions), y evita
# tener secretos guardados en el disco o commiteados por accidente.
provider "aws" {
  region = var.aws_region


  # A absolutamente TODO lo que construyas a partir de ahora, pégale automáticamente 
  # una etiqueta que diga Project = Anybuddy y ManagedBy = terraform". 
  # Así, cuando veas la factura de AWS, sabrás exactamente qué gastó este proyecto.
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
