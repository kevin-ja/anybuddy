# Consulta a AWS para obtener la lista de zonas de disponibilidad (data centers) 
# que están activas en tu región. No crea nada, solo consulta información.
data "aws_availability_zones" "available" {
  state = "available"
}

# Crea la VPC, que es tu espacio de red privado e aislado en la nube de AWS. 
# Habilita los nombres DNS para que los recursos puedan identificarse mediante 
# dominios y no solo por IP.
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

#Crea el "módem" o puerta de enlace y lo conecta a tu VPC. Sin este recurso, 
# la VPC no tendría forma de comunicarse con el mundo exterior
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project}-igw"
  }
}

# Crea una subred (una parcela o subdivisión dentro de tu VPC)
# Configura la subred para que asigne automáticamente direcciones IP públicas a
# los servidores o recursos que se creen allí.
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project}-public-subnet"
  }
}

# Define las reglas de navegación para la red. En este caso, establece que todo
#  el tráfico hacia Internet (0.0.0.0/
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project}-public-rt"
  }
}

#  Enlaza la tabla de enrutamiento con la subred pública. Esto es lo que finalmente 
# convierte a la subred en "pública", ya que le otorga las reglas necesarias 
# para enviar y recibir tráfico desde Internet.
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
