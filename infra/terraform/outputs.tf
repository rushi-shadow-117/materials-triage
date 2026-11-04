output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "db_address" {
  value = aws_db_instance.postgres.address
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "secrets_to_fill" {
  description = "Secrets Manager entries the operator fills after apply."
  value       = [for s in aws_secretsmanager_secret.keys : s.name]
}
