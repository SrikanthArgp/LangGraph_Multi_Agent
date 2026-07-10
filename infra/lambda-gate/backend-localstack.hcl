# Concrete S3-backend config for the LocalStack pass. Supply at init time:
#   terraform init -backend-config=backend-localstack.hcl
#
# Bucket/table names must match infra/bootstrap/main.tf's state_bucket_name /
# state_lock_table_name outputs — run bootstrap's apply first.
#
# NOTE: the S3 backend's exact argument names for endpoint overrides and path-style
# addressing have changed across Terraform versions (older: `endpoint` + `force_path_style`;
# newer: nested `endpoints { s3 = ... }` + `use_path_style`). This file uses the older,
# longer-standing names — if `terraform init` errors on an unrecognized argument here,
# check `terraform init -help` / the aws backend docs for whichever your installed Terraform
# version (currently 1.15.7) expects, and swap accordingly. Flagging this rather than
# asserting it, since it's the one thing here I can't verify without actually running init.
bucket                      = "crag-terraform-state"
key                         = "crag/prod/lambda-gate/terraform.tfstate" # scoped under this module's own prefix — infra/fargate/ uses a sibling key so the two root modules' state never collide
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
