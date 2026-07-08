provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # LocalStack doesn't validate real AWS credentials/account/region the way real AWS does —
  # these three "skip_*" flags turn off checks that would otherwise fail against a fake
  # endpoint. access_key/secret_key = "test" is LocalStack's documented placeholder pair, not
  # a real secret (real AWS would reject it outright), so it's fine to leave inline here rather
  # than pull from a var — nothing sensitive to protect.
  access_key                  = var.use_localstack ? "test" : null
  secret_key                  = var.use_localstack ? "test" : null
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack

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
