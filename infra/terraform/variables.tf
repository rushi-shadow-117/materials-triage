variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for every resource."
  type        = string
  default     = "materials-triage"
}

variable "image" {
  description = "The api image, pushed to ECR by the operator (for example <account>.dkr.ecr.<region>.amazonaws.com/materials-triage:api)."
  type        = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "api_cpu" {
  description = "Fargate CPU units for the api task."
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the api task."
  type        = number
  default     = 4096
}

variable "public_endpoint" {
  description = "Create an internet-facing load balancer. Off by default: nothing public is left running unless an operator asks for it."
  type        = bool
  default     = false
}

variable "allowed_cidrs" {
  description = "CIDRs that may reach the load balancer when public_endpoint is true."
  type        = list(string)
  default     = []
}

variable "settings" {
  description = "Non-secret environment for the api task (AUTH_MODE, OIDC_*, LLM_PROVIDER, LLM_MODEL, CLASSIFY_MODE, FETCH_MODE)."
  type        = map(string)
  default = {
    AUTH_MODE     = "oidc"
    SITE_MODE     = "true"
    LLM_PROVIDER  = "anthropic"
    LLM_MODEL     = "claude-sonnet-5-5"
    CLASSIFY_MODE = "cache_only"
    FETCH_MODE    = "live"
  }
}
