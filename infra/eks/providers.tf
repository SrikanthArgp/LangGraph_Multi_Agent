provider "aws" {
  region = var.aws_region

  # See infra/lambda-gate/providers.tf's identical comment — profile is gated behind
  # use_localstack for the same reason: an ephemeral ubuntu-latest CD runner authenticating via
  # OIDC-minted env-var credentials has no "localstack"-named AWS CLI profile to resolve. Phase
  # 20/21's deploy is manual-only though (plan.md step 8) — this stays for parity with the other
  # two stacks, not because a CD runner actually applies this one.
  profile = var.use_localstack ? var.aws_profile : null

  # See infra/bootstrap/main.tf's provider block for what each of these does — identical
  # reasoning, duplicated here because Terraform provider blocks can't be shared/imported across
  # root modules.
  access_key                  = var.use_localstack ? "test" : null
  secret_key                  = var.use_localstack ? "test" : null
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  s3_use_path_style           = var.use_localstack

  # Every service this phase's architecture touches (plan.md's Phase 20), routed at LocalStack's
  # single edge port (4566) when use_localstack — real AWS resolves each service's normal
  # regional endpoint instead, so this block is skipped entirely there. eks itself is flagged in
  # plan.md step 7 as the least-mature of the three LocalStack emulations used across this repo
  # (it stands up a real local cluster behind the mocked EKS API, rather than emulating a real
  # control plane the way Lambda/API Gateway do) — expect gaps here sooner than in
  # infra/lambda-gate/ or infra/fargate/.
  dynamic "endpoints" {
    for_each = var.use_localstack ? [1] : []
    content {
      s3  = "http://localhost:4566"
      iam = "http://localhost:4566"
      sts = "http://localhost:4566"
      ecr = "http://localhost:4566"
      ssm = "http://localhost:4566"
      kms = "http://localhost:4566"
      ec2 = "http://localhost:4566"
      eks = "http://localhost:4566"
    }
  }
}
