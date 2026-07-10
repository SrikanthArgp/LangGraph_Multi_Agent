provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # See infra/bootstrap/main.tf's provider block for what each of these does — identical
  # reasoning, duplicated here because Terraform provider blocks can't be shared/imported
  # across root modules.
  access_key                  = var.use_localstack ? "test" : null
  secret_key                  = var.use_localstack ? "test" : null
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  s3_use_path_style           = var.use_localstack

  # Every service this phase's architecture touches (per enterprize-deploy-steps.md's wiring
  # table), routed at LocalStack's single edge port (4566) when use_localstack — real AWS
  # resolves each service's normal regional endpoint instead, so this block is skipped
  # entirely there. apigatewayv2 and cloudfront specifically need LocalStack Pro/Ultimate,
  # not the free Community edition — the rest (s3, dynamodb, iam, sts, lambda, ecr, ssm,
  # logs, kms) work on Community.
  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3             = "http://localhost:4566"
      dynamodb       = "http://localhost:4566"
      iam            = "http://localhost:4566"
      sts            = "http://localhost:4566"
      lambda         = "http://localhost:4566"
      ecr            = "http://localhost:4566"
      ssm            = "http://localhost:4566"
      cloudwatchlogs = "http://localhost:4566"
      kms            = "http://localhost:4566"
      apigatewayv2   = "http://localhost:4566"
      cloudfront     = "http://localhost:4566"
    }
  }
}
