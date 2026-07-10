variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "localstack"
}

# Flips every LocalStack-only provider setting in providers.tf. Set to false
# (-var="use_localstack=false") once this same config is re-pointed at real AWS.
variable "use_localstack" {
  type    = bool
  default = true
}

# Same project/environment defaults as infra/lambda-gate/, but this module never reads or
# references that module's state, resources, or SSM parameters — its own ECR repo (ecr.tf), SSM
# secrets (ssm.tf), and every other resource are entirely independent. Resource names that must
# be unique across both stacks (ECR repo, S3 bucket, ALB, ECS cluster/service, VPC, SSM path) get
# an explicit "-ecs" component (local.name_prefix / local.ssm_prefix, network.tf) so they never
# collide with infra/lambda-gate/'s same-named resources.
variable "project_name" {
  type    = string
  default = "crag"
}

variable "environment" {
  type    = string
  default = "prod"
}

# Tag pushed to this stack's own ECR repo (ecr.tf) by infra/fargate/scripts/push_image.sh.
variable "backend_image_tag" {
  type    = string
  default = "latest"
}

# Every secret backend/config.py's _SSM_SECRET_KEYS expects, same as
# infra/lambda-gate/variables.tf's var.secrets — populated from this stack's own
# infra/fargate/secrets.auto.tfvars (gitignored), a deliberate duplicate of
# infra/lambda-gate/secrets.auto.tfvars kept in sync by hand (see ssm.tf).
variable "secrets" {
  type      = map(string)
  sensitive = true
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# Cheapest Fargate size (plan.md Phase 16 step 2) — 0.25 vCPU / 0.5 GB.
variable "task_cpu" {
  type    = string
  default = "256"
}

variable "task_memory" {
  type    = string
  default = "512"
}

# Single instance, no HA — a deliberate cost/availability tradeoff for a learning deployment
# (plan.md Phase 16 step 2), not an oversight.
variable "desired_count" {
  type    = number
  default = 1
}

# Matches backend/run_api.py's hardcoded uvicorn.run(..., port=8000) — same port Lambda's
# adapter proxies to via PORT=8000 in backend/Dockerfile, reused unchanged here since this is
# the same image with a real load balancer in front instead of the adapter.
variable "container_port" {
  type    = number
  default = 8000
}

# Target-tracking autoscaling threshold (plan.md Phase 16 step 4).
variable "cpu_target_value" {
  type    = number
  default = 70
}

variable "min_task_count" {
  type    = number
  default = 1
}

variable "max_task_count" {
  type    = number
  default = 3
}
