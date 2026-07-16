terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Kept empty here on purpose — Terraform backend blocks can't reference variables, so the
  # concrete bucket/table/endpoint values are supplied at `terraform init` time via
  # -backend-config=backend-localstack.hcl (or backend-aws.hcl against real AWS). Run
  # infra/bootstrap/ first to create the bucket + table this points at — shared with
  # infra/lambda-gate/ and infra/fargate/, just under this module's own state key (see
  # backend-*.hcl).
  backend "s3" {}
}
