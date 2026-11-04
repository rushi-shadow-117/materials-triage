# Terraform reference module

A reference deployment on AWS, validated in CI (`terraform fmt -check`, `terraform validate`
with the provider pinned) and never applied from this repository. Docker Compose remains the
primary deployment.

What it creates: a VPC with two private and two public subnets, one NAT gateway, Postgres 16
on RDS in the private subnets, an ECS Fargate service running the `api` image, Secrets
Manager entries for the keys and the database URL, CloudWatch logs, and, only when
`public_endpoint = true`, an application load balancer limited to `allowed_cidrs`. Nothing
public is created by default.

## Egress

The api task's security group allows outbound HTTPS, and the private subnets route it
through the NAT gateway. Security groups filter by IP and port, not by hostname. The host
allowlist (Materials Project, OpenAlex, PubChem, the model endpoint) is enforced by the
application's egress check in `src/materials_triage/adapters/egress.py`; a network-level
domain allowlist needs an egress proxy or AWS Network Firewall domain rules, which this
module does not include.

## Apply (outside this repository)

```
docker build --target api -t materials-triage:api . && docker tag ... && docker push <ecr>
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply -var image=<ecr>/materials-triage:api
```

Then fill the secrets listed in the `secrets_to_fill` output, run the migration once from a
task or a bastion (`alembic upgrade head` with the migrate role; this module creates one
database user, so create the three roles from `provenance/roles.sql` first), and set the
`OIDC_*` values in `var.settings` for your identity provider.

Cost: a NAT gateway and a `db.t4g.small` instance run continuously; the Fargate task is one
vCPU and 4 GiB. Not covered: a managed identity provider, TLS certificates for the load
balancer, the maintenance role's retention job, and multi-AZ for the database.
