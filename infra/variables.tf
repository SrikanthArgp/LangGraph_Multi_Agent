variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "localstack"
}

# Flips every LocalStack-only provider setting in providers.tf. Set to false
# (-var="use_localstack=false") once this same config is re-pointed at real AWS in Stage C —
# resource definitions don't change, only this and the backend config file do.
variable "use_localstack" {
  type    = bool
  default = true
}

# Used to namespace resource names/tags and the SSM parameter path prefix (/{project_name}/{environment}/*),
# matching enterprize-deploy-steps.md's wiring table.
variable "project_name" {
  type    = string
  default = "crag"
}

variable "environment" {
  type    = string
  default = "prod"
}

# Every secret backend/config.py's _SSM_SECRET_KEYS expects at /{project_name}/{environment}/<KEY>.
# Populated from infra/secrets.auto.tfvars (gitignored — mirrors backend/.env, except REDIS_URL,
# which must be the real Upstash rediss:// URL, not the local-Redis value backend/.env holds).
variable "secrets" {
  type      = map(string)
  sensitive = true
}

# Tag pushed to the ECR repo by infra/scripts/push_image.sh — bump when re-pushing a new image
# so aws_lambda_function.backend's image_uri actually changes and Terraform picks it up.
variable "backend_image_tag" {
  type    = string
  default = "latest"
}

# Explicit CloudWatch Logs retention for the Lambda log group, so it doesn't fall back to
# "never expire" (the AWS default for an auto-created log group).
variable "log_retention_days" {
  type    = number
  default = 14
}
