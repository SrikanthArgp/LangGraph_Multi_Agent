# Concrete S3-backend config for real AWS.
#   terraform init -backend-config=backend-aws.hcl
#
# Bucket must already exist (via infra/bootstrap/ run with -var="use_localstack=false" against a
# real AWS profile — already done, per infra/fargate/backend-aws.hcl's comment: applied 2026-07-13,
# account-ID-suffixed for global S3-bucket-name uniqueness). Same bucket infra/lambda-gate/ and
# infra/fargate/ both already point at — must match their bucket name exactly, only the `key`
# differs.
bucket         = "crag-terraform-state-247673029324" # account-ID-suffixed, per infra/bootstrap/ apply on 2026-07-13 — same bucket as infra/lambda-gate/ and infra/fargate/
key            = "crag/prod/eks/terraform.tfstate"    # sibling key to the other two stacks' — same bucket, never the same object
region         = "us-east-1"
dynamodb_table = "crag-terraform-locks"
