terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # No backend block here on purpose: this root's own state stays local. It creates the
  # S3 bucket + DynamoDB table that every other infra/ root module's "s3" backend depends on
  # (infra/lambda-gate/, infra/fargate/, ...), so it can't itself depend on a backend that
  # doesn't exist yet.
}
