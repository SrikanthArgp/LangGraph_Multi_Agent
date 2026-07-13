# Concrete S3-backend config for real AWS. Placeholder — fill in once actually deploying to a
# real account: bucket/table must exist (via infra/bootstrap/ run with
# -var="use_localstack=false" against a real AWS profile), and the bucket name must be globally
# unique across all of S3, not just this account, so "crag-terraform-state" will very likely need
# a suffix (account ID, random string) at that point — must match whatever suffix
# infra/lambda-gate/backend-aws.hcl ends up using, since both point at the same bucket.
#
#   terraform init -backend-config=backend-aws.hcl
bucket         = "crag-terraform-state-247673029324" # account-ID-suffixed for global S3-bucket-name uniqueness, per infra/bootstrap/ apply on 2026-07-13
key            = "crag/prod/fargate/terraform.tfstate" # sibling key to infra/lambda-gate/'s "crag/prod/lambda-gate/terraform.tfstate" — same bucket, never the same object
region         = "us-east-1"
dynamodb_table = "crag-terraform-locks"
