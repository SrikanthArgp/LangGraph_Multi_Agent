# Concrete S3-backend config for Stage C (real AWS). Placeholder — fill in once actually
# deploying to a real account: bucket/table must exist (via infra/bootstrap/ run with
# -var="use_localstack=false" against a real AWS profile), and bucket names must be
# globally unique across all of S3, not just this account, so "crag-terraform-state" will
# very likely need a suffix (account ID, random string) at that point.
#
#   terraform init -backend-config=backend-aws.hcl
bucket         = "crag-terraform-state-247673029324" # account-ID-suffixed for global S3-bucket-name uniqueness, per infra/bootstrap/ apply on 2026-07-13
key            = "crag/prod/lambda-gate/terraform.tfstate" # scoped under this module's own prefix — infra/fargate/ uses a sibling key so the two root modules' state never collide
region         = "us-east-1"
dynamodb_table = "crag-terraform-locks"
