variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "localstack"
}

# Was `data "aws_caller_identity" "current" {}` in github-oidc.tf (a live STS GetCallerIdentity
# call) until 2026-07-16, when that call was found to hang indefinitely via the Go AWS SDK on this
# dev machine specifically (confirmed: the exact same call succeeds instantly via `aws sts
# get-caller-identity`/`aws iam list-roles` through the CLI, and every other AWS provider call in
# this repo's other Terraform stacks worked fine in the same session — isolated to this one call
# pattern, root cause not identified, multiple standard workarounds tried and ruled out: TLS 1.3
# disable, -refresh=false, skip_credentials_validation, regional vs. global STS endpoint). Default
# is this account's real ID, already confirmed via CLI multiple times this session.
variable "aws_account_id" {
  type    = string
  default = "247673029324"
}

# Flips every LocalStack-only provider setting below. Set to false (via
# -var="use_localstack=false") once pointing this same config at real AWS in Stage C.
variable "use_localstack" {
  type    = bool
  default = true
}

variable "state_bucket_name" {
  type    = string
  default = "crag-terraform-state"
}

variable "state_lock_table_name" {
  type    = string
  default = "crag-terraform-locks"
}
