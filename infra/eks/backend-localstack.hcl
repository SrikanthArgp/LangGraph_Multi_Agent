# Concrete S3-backend config for the LocalStack pass. Supply at init time:
#   terraform init -backend-config=backend-localstack.hcl
#
# Bucket/table names must match infra/bootstrap/main.tf's state_bucket_name / state_lock_table_name
# outputs — run bootstrap's apply first (LocalStack state doesn't persist across container
# restarts here, persistence is disabled — see grand-enterprize-deploy-steps.md's recurring
# "LocalStack was reset" recovery note; re-apply infra/bootstrap/ whenever the container is fresh,
# before this init). Shared bucket with infra/lambda-gate/ and infra/fargate/, distinct key — see
# the comment on `key` below.
#
# NOTE: the S3 backend's exact argument names for endpoint overrides and path-style addressing
# have changed across Terraform versions (older: `endpoint` + `force_path_style`; newer: nested
# `endpoints { s3 = ... }` + `use_path_style`). This file uses the older, longer-standing names —
# if `terraform init` errors on an unrecognized argument here, check `terraform init -help` / the
# aws backend docs for whichever your installed Terraform version expects, and swap accordingly.
bucket                      = "crag-terraform-state"
key                         = "crag/prod/eks/terraform.tfstate" # sibling key to infra/lambda-gate's "crag/prod/lambda-gate/terraform.tfstate" and infra/fargate's "crag/prod/fargate/terraform.tfstate" — same bucket, never the same object
region                      = "us-east-1"
dynamodb_table              = "crag-terraform-locks"
endpoint                    = "http://localhost:4566"
dynamodb_endpoint           = "http://localhost:4566"
iam_endpoint                = "http://localhost:4566"
sts_endpoint                = "http://localhost:4566"
access_key                  = "test"
secret_key                  = "test"
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_region_validation      = true
force_path_style            = true
