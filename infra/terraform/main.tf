# Reference deployment: a VPC with private subnets, Postgres on RDS, the api image on ECS
# Fargate, secrets in Secrets Manager, egress through a NAT gateway. Validated in CI, never
# applied here. Security groups filter by IP and port, not by hostname: the application's
# egress check (adapters/egress.py) enforces the host allowlist, and a network-level domain
# allowlist needs an egress proxy or AWS Network Firewall domain rules, which this module does
# not include. See README.md in this directory.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs             = slice(data.aws_availability_zones.available.names, 0, 2)
  private_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  public_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, 10 + i)]
  tags            = { project = var.name, managed_by = "terraform" }
}

# ----------------------------------------------------------------------------- network

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = var.name })
}

resource "aws_subnet" "private" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_subnets[count.index]
  availability_zone = local.azs[count.index]
  tags              = merge(local.tags, { Name = "${var.name}-private-${count.index}" })
}

resource "aws_subnet" "public" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.public_subnets[count.index]
  availability_zone = local.azs[count.index]
  tags              = merge(local.tags, { Name = "${var.name}-public-${count.index}" })
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = local.tags
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = local.tags
}

# All outbound traffic from the private subnets leaves through one NAT gateway.
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = local.tags
  depends_on    = [aws_internet_gateway.igw]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = local.tags
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = local.tags
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ----------------------------------------------------------------------------- security groups

resource "aws_security_group" "api" {
  name        = "${var.name}-api"
  description = "api task: HTTPS out through the NAT gateway; the host allowlist is enforced by the application"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS to the upstream APIs and the model provider (by IP; hostnames are checked in code)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "Postgres from the api task only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  tags = local.tags
}

resource "aws_security_group_rule" "api_to_db" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.db.id
}

# ----------------------------------------------------------------------------- database

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "db" {
  name       = "${var.name}-db"
  subnet_ids = aws_subnet.private[*].id
  tags       = local.tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.name}-db"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  db_name                 = "triage"
  username                = "triage"
  password                = random_password.db.result
  db_subnet_group_name    = aws_db_subnet_group.db.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  publicly_accessible     = false
  skip_final_snapshot     = true
  backup_retention_period = 7
  tags                    = local.tags
}

# ----------------------------------------------------------------------------- secrets

# The operator fills the values after apply; nothing secret is in this module.
resource "aws_secretsmanager_secret" "keys" {
  for_each = toset(["MP_API_KEY", "OPENALEX_API_KEY", "ANTHROPIC_API_KEY"])
  name     = "${var.name}/${each.key}"
  tags     = local.tags
}

resource "aws_secretsmanager_secret" "db_url" {
  name = "${var.name}/DATABASE_URL"
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = "postgresql+psycopg://triage:${random_password.db.result}@${aws_db_instance.postgres.address}:5432/triage"
}

# ----------------------------------------------------------------------------- ECS

resource "aws_ecs_cluster" "main" {
  name = var.name
  tags = local.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${var.name}/api"
  retention_in_days = 30
  tags              = local.tags
}

data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = concat([for s in aws_secretsmanager_secret.keys : s.arn], [aws_secretsmanager_secret.db_url.arn])
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.name}-read-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = var.image
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = [for k, v in var.settings : { name = k, value = v }]
      secrets = concat(
        [for k, s in aws_secretsmanager_secret.keys : { name = k, valueFrom = s.arn }],
        [{ name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url.arn }]
      )
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.public_endpoint ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api[0].arn
      container_name   = "api"
      container_port   = 8000
    }
  }

  tags = local.tags
}

# ----------------------------------------------------------------------------- optional public endpoint

resource "aws_security_group" "lb" {
  count       = var.public_endpoint ? 1 : 0
  name        = "${var.name}-lb"
  description = "Load balancer: HTTPS from the allowed CIDRs"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  egress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  tags = local.tags
}

resource "aws_security_group_rule" "lb_to_api" {
  count                    = var.public_endpoint ? 1 : 0
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.api.id
  source_security_group_id = aws_security_group.lb[0].id
}

resource "aws_lb" "api" {
  count              = var.public_endpoint ? 1 : 0
  name               = "${var.name}-lb"
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.lb[0].id]
  tags               = local.tags
}

resource "aws_lb_target_group" "api" {
  count       = var.public_endpoint ? 1 : 0
  name        = "${var.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path = "/health"
  }

  tags = local.tags
}
