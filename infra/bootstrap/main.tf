provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # LocalStack doesn't validate real AWS credentials/account/region the way real AWS does —
  # these three "skip_*" flags turn off checks that would otherwise fail against a fake
  # endpoint. access_key/secret_key = "test" is LocalStack's documented placeholder pair, not
  # a real secret (real AWS would reject it outright), so it's fine to leave inline here rather
  # than pull from a var — nothing sensitive to protect.
  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null
  # skip_credentials_validation/skip_requesting_account_id forced to true unconditionally
  # (2026-07-16), not tied to var.use_localstack like skip_metadata_api_check below — the AWS
  # provider's own internal validation call (its ConfigureProvider-time STS GetCallerIdentity
  # equivalent) was found to hang indefinitely via the Go AWS SDK on this dev machine against real
  # AWS specifically, empirically confirmed across multiple bounded test runs: every run with this
  # left at var.use_localstack (false for real AWS) hung immediately after the first data source
  # read and never progressed; every run with it forced true got past that point and successfully
  # refreshed real resources. Real credentials/connectivity independently confirmed fine via the
  # `aws` CLI throughout (sts get-caller-identity, iam list-roles, raw curl to iam.amazonaws.com —
  # all instant) — this isn't skipping a check because credentials are bad, it's avoiding a
  # specific Go-SDK call pattern that hangs on this machine's network path. See variables.tf's
  # aws_account_id comment for the matching fix to github-oidc.tf's own explicit instance of the
  # same call pattern (data "aws_caller_identity" "current").
  skip_credentials_validation = true
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = true

  # S3 path-style addressing (bucket.name in the URL PATH, not as a subdomain) — LocalStack's
  # S3 emulation doesn't support virtual-hosted-style (subdomain) requests the way real S3 does.
  s3_use_path_style = var.use_localstack

  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3       = "http://localhost:4566"
      dynamodb = "http://localhost:4566"
      iam      = "http://localhost:4566"
      sts      = "http://localhost:4566"
    }
  }
}

resource "aws_s3_bucket" "tfstate" {
  bucket = var.state_bucket_name

  # Safety net against `terraform destroy` accidentally taking the state bucket down with
  # everything else — irrelevant on LocalStack (state resets with the container anyway) but
  # this same config gets re-pointed at real AWS in Stage C unchanged.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_dynamodb_table" "tflock" {
  name         = var.state_lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket_name" {
  value = aws_s3_bucket.tfstate.id
}

output "state_lock_table_name" {
  value = aws_dynamodb_table.tflock.id
}
