# GitHub's OIDC identity provider — one per AWS account, shared by every workflow/role that
# assumes a role via token.actions.githubusercontent.com. Registered here (not in
# infra/lambda-gate/ or infra/fargate/) because it's account-level and shared by both deploy
# roles below, matching plan.md's Phase 18 step 1 clarification: "the provider is shared; the
# deploy role is not." See real-aws-cicd-setup.md for the full rationale/walkthrough.
data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

locals {
  github_repo = "SrikanthArgp/SearchAssistantProduction"
}

# ---------------------------------------------------------------------------
# cd-lambda-deploy-role — used by cd-lambda.yml in `aws` mode only.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "cd_lambda_deploy" {
  name = "cd-lambda-deploy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        # Restricted to pushes to main specifically — not repo:<owner>/* or a wildcard ref.
        # Too broad here lets any branch (or any repo under the owner) assume this role.
        StringLike = { "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "cd_lambda_terraform_state" {
  name = "terraform-state"
  role = aws_iam_role.cd_lambda_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}"
        Condition = { StringLike = { "s3:prefix" = ["crag/prod/lambda-gate/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}/crag/prod/lambda-gate/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:*:*:table/crag-terraform-locks"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_lambda_ecr" {
  name = "ecr"
  role = aws_iam_role.cd_lambda_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      {
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository", "ecr:DescribeRepositories", "ecr:DeleteRepository",
          "ecr:TagResource", "ecr:ListTagsForResource",
          "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
          "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
          # Needed for aws_ecr_repository_policy.backend (ecr.tf) — granting the Lambda service
          # itself pull access, a real requirement found on the first full apply (see ecr.tf's
          # header comment), not present in the original design.
          "ecr:SetRepositoryPolicy", "ecr:GetRepositoryPolicy", "ecr:DeleteRepositoryPolicy",
        ]
        Resource = "arn:aws:ecr:*:*:repository/crag-backend"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_lambda_compute" {
  name = "compute"
  role = aws_iam_role.cd_lambda_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
          "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:DeleteFunction",
          "lambda:AddPermission", "lambda:RemovePermission", "lambda:GetPolicy", "lambda:TagResource", "lambda:ListTags",
          "lambda:ListVersionsByFunction",
          "lambda:CreateFunctionUrlConfig", "lambda:GetFunctionUrlConfig",
          "lambda:UpdateFunctionUrlConfig", "lambda:DeleteFunctionUrlConfig",
        ]
        Resource = "arn:aws:lambda:*:*:function:crag-prod-backend*"
      },
      # apigatewayv2 has no useful resource-level ARN restriction for most of these actions —
      # scoped to the service instead, same tradeoff every apigatewayv2 Terraform role makes.
      { Effect = "Allow", Action = ["apigateway:*"], Resource = "arn:aws:apigateway:*::/apis*" },
      # CloudFront, its cache/origin-request policies, and OACs don't support resource-level
      # IAM restriction at all (AWS-wide limitation, not a scoping choice made here).
      { Effect = "Allow", Action = ["cloudfront:*"], Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:TagResource", "logs:ListTagsForResource", "logs:ListTagsLogGroup"]
        Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/crag-prod-backend*"
      },
      # logs:DescribeLogGroups and ssm:DescribeParameters are both account/region-wide List-style
      # APIs — AWS doesn't support resource-level restriction for either at all (confirmed by the
      # first real apply: scoping DescribeLogGroups to a specific log-group ARN was denied
      # outright, not just under-scoped), so they can't join the resource-scoped statements above.
      { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*" },
      { Effect = "Allow", Action = ["ssm:DescribeParameters"], Resource = "*" },
      {
        # s3:Get*/s3:List* rather than enumerating individual read calls — the AWS provider's
        # aws_s3_bucket refresh hits a wide, version-dependent set of Get* sub-APIs (ACL, tagging,
        # versioning, CORS, etc.) regardless of which of those are actually configured on the
        # resource; found missing s3:GetBucketAcl specifically on the first real apply, and
        # narrowing this further just risks the same one-at-a-time gap on the next attribute.
        Effect   = "Allow"
        Action   = ["s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketPublicAccessBlock", "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:Get*", "s3:List*"]
        Resource = ["arn:aws:s3:::crag-prod-frontend", "arn:aws:s3:::crag-prod-frontend/*"]
      },
      {
        Effect   = "Allow"
        # ssm:GetParameters (plural, batch-get) is a distinct IAM action from ssm:GetParameter
        # (singular) — found missing here because SSM's own ListTagsForResource implementation
        # calls the plural API internally, not something obvious from the action name alone.
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:PutParameter", "ssm:DeleteParameter", "ssm:AddTagsToResource", "ssm:ListTagsForResource"]
        Resource = "arn:aws:ssm:*:*:parameter/crag/prod/*"
      },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = "arn:aws:kms:*:*:alias/aws/ssm" },
      {
        # Needed only on the full-apply (infra-changed) path — Terraform re-asserts
        # lambda_exec's role on every apply, even when the role itself is unchanged.
        Effect   = "Allow"
        # iam:ListInstanceProfilesForRole: the AWS provider's role-delete path checks for
        # attached instance profiles before deleting, unconditionally, even though a Lambda/ECS
        # execution role would never have one — found because a previous partial apply left this
        # role "tainted" (a create succeeded but a later read in the same apply errored,
        # confirmed in the run log: "is tainted, so must be replaced"), forcing a destroy+recreate
        # on this attempt.
        Action   = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:TagRole", "iam:ListRoleTags", "iam:PassRole"]
        Resource = "arn:aws:iam::*:role/crag-prod-lambda-exec"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# cd-ecs-deploy-role — used by cd-ecs.yml in `aws` mode only. Independent of the role above:
# no shared trust policy, no lambda:* permissions.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "cd_ecs_deploy" {
  name = "cd-ecs-deploy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "cd_ecs_terraform_state" {
  name = "terraform-state"
  role = aws_iam_role.cd_ecs_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}"
        Condition = { StringLike = { "s3:prefix" = ["crag/prod/fargate/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}/crag/prod/fargate/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:*:*:table/crag-terraform-locks"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_ecs_ecr" {
  name = "ecr"
  role = aws_iam_role.cd_ecs_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      {
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository", "ecr:DescribeRepositories", "ecr:DeleteRepository",
          "ecr:TagResource", "ecr:ListTagsForResource",
          "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
          "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
        ]
        Resource = "arn:aws:ecr:*:*:repository/crag-prod-ecs-backend"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_ecs_compute" {
  name = "compute"
  role = aws_iam_role.cd_ecs_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:*"]
        Resource = ["arn:aws:ecs:*:*:cluster/crag-prod-ecs", "arn:aws:ecs:*:*:service/crag-prod-ecs/*", "arn:aws:ecs:*:*:task-definition/crag-prod-ecs-backend:*"]
      },
      # register/deregister-task-definition have no useful resource-level restriction.
      # ecs:DeregisterTaskDefinition found missing on the first real-AWS full apply: Terraform
      # calls it when aws_ecs_task_definition.backend is replaced (destroy+recreate), not just on
      # a plain `terraform destroy`.
      { Effect = "Allow", Action = ["ecs:RegisterTaskDefinition", "ecs:DeregisterTaskDefinition", "ecs:DescribeTaskDefinition"], Resource = "*" },
      # VPC/subnet/IGW/route-table/security-group/ALB/target-group creation calls largely don't
      # support resource-level IAM restriction either (standard EC2/ELB limitation) — scoped to
      # the service namespace, same tradeoff as CloudFront above.
      { Effect = "Allow", Action = ["ec2:*"], Resource = "*" },
      { Effect = "Allow", Action = ["elasticloadbalancing:*"], Resource = "*" },
      { Effect = "Allow", Action = ["application-autoscaling:*"], Resource = "*" },
      { Effect = "Allow", Action = ["cloudfront:*"], Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:TagResource", "logs:ListTagsForResource", "logs:ListTagsLogGroup"]
        Resource = "arn:aws:logs:*:*:log-group:/ecs/crag-prod-ecs*"
      },
      # See infra/lambda-gate's identical statements/comment above — DescribeLogGroups and
      # DescribeParameters don't support resource-level restriction at all.
      { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*" },
      { Effect = "Allow", Action = ["ssm:DescribeParameters"], Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketPublicAccessBlock", "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:Get*", "s3:List*"]
        Resource = ["arn:aws:s3:::crag-prod-ecs-frontend", "arn:aws:s3:::crag-prod-ecs-frontend/*"]
      },
      {
        Effect   = "Allow"
        # ssm:GetParameters (plural, batch-get) is a distinct IAM action from ssm:GetParameter
        # (singular) — found missing here because SSM's own ListTagsForResource implementation
        # calls the plural API internally, not something obvious from the action name alone.
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:PutParameter", "ssm:DeleteParameter", "ssm:AddTagsToResource", "ssm:ListTagsForResource"]
        Resource = "arn:aws:ssm:*:*:parameter/crag/prod-ecs/*"
      },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = "arn:aws:kms:*:*:alias/aws/ssm" },
      {
        Effect   = "Allow"
        # iam:ListInstanceProfilesForRole: the AWS provider's role-delete path checks for
        # attached instance profiles before deleting, unconditionally, even though a Lambda/ECS
        # execution role would never have one — found because a previous partial apply left this
        # role "tainted" (a create succeeded but a later read in the same apply errored,
        # confirmed in the run log: "is tainted, so must be replaced"), forcing a destroy+recreate
        # on this attempt.
        Action   = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:TagRole", "iam:ListRoleTags", "iam:PassRole"]
        Resource = ["arn:aws:iam::*:role/crag-prod-ecs-execution", "arn:aws:iam::*:role/crag-prod-ecs-task"]
      },
      {
        # First-time-in-account only: ECS and ELB each need a service-linked role
        # (AWSServiceRoleForECS / AWSServiceRoleForElasticLoadBalancing) that AWS creates
        # automatically the first time either service is used — but the calling principal
        # needs permission to trigger that creation. No-op (AlreadyExists, harmless) on every
        # apply after the first.
        Effect   = "Allow"
        Action   = ["iam:CreateServiceLinkedRole"]
        Resource = "arn:aws:iam::*:role/aws-service-role/*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# cd-eks-deploy-role — used by cd-eks.yml in `aws` mode only. Independent of the two roles above:
# no shared trust policy, no lambda:*/ecs:* permissions. Phase 21 (2026-07-16).
#
# Broader than cd_lambda_deploy/cd_ecs_deploy's "ECR push only" original design (see
# project_phase21_argocd_in_progress memory) — cd-eks.yml mirrors cd-lambda.yml/cd-ecs.yml's own
# fast-path/full-apply shape exactly, per explicit instruction, so it needs the same
# infra-can-change-too surface those two have, generalized to EKS's resource types. Deliberately
# does NOT include any eks:AccessKubernetesApi-equivalent or kubectl-facing permission — this role
# only ever runs `terraform apply` against infra/eks/ and pushes a git commit; verifying the actual
# in-cluster rollout is ArgoCD's job (already proven working manually this session), not this
# role's.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "cd_eks_deploy" {
  name = "cd-eks-deploy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "cd_eks_terraform_state" {
  name = "terraform-state"
  role = aws_iam_role.cd_eks_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}"
        Condition = { StringLike = { "s3:prefix" = ["crag/prod/eks/*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::crag-terraform-state-${var.aws_account_id}/crag/prod/eks/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = "arn:aws:dynamodb:*:*:table/crag-terraform-locks"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_eks_ecr" {
  name = "ecr"
  role = aws_iam_role.cd_eks_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      {
        Effect = "Allow"
        Action = [
          "ecr:CreateRepository", "ecr:DescribeRepositories", "ecr:DeleteRepository",
          "ecr:TagResource", "ecr:ListTagsForResource",
          "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage",
          "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
        ]
        Resource = "arn:aws:ecr:*:*:repository/crag-prod-eks-backend"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cd_eks_compute" {
  name = "compute"
  role = aws_iam_role.cd_eks_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # eks:* on "*" — same "service doesn't support useful resource-level restriction for most of
      # its own actions" tradeoff this file already makes for apigateway:*/cloudfront:*/ec2:*/
      # elasticloadbalancing:* below, not a scoping choice unique to this role.
      { Effect = "Allow", Action = ["eks:*"], Resource = "*" },
      # VPC/subnet/IGW/route-table/security-group creation calls largely don't support
      # resource-level IAM restriction either (standard EC2 limitation) — same tradeoff
      # cd_ecs_deploy's identical grant already makes.
      { Effect = "Allow", Action = ["ec2:*"], Resource = "*" },
      # Needed for cloudfront.tf's data "aws_lb" tag-based lookup of the ALB the Load Balancer
      # Controller provisions out-of-band — this role never creates the ALB itself (Kubernetes
      # does), only ever reads it.
      { Effect = "Allow", Action = ["elasticloadbalancing:*"], Resource = "*" },
      { Effect = "Allow", Action = ["cloudfront:*"], Resource = "*" },
      {
        Effect   = "Allow"
        Action   = ["s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketPublicAccessBlock", "s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:Get*", "s3:List*"]
        Resource = ["arn:aws:s3:::crag-prod-eks-frontend", "arn:aws:s3:::crag-prod-eks-frontend/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath", "ssm:PutParameter", "ssm:DeleteParameter", "ssm:AddTagsToResource", "ssm:ListTagsForResource", "ssm:DescribeParameters"]
        Resource = "arn:aws:ssm:*:*:parameter/crag/prod-eks/*"
      },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = "arn:aws:kms:*:*:alias/aws/ssm" },
      { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*" },
      {
        # Scoped to this stack's own 4 roles (infra/eks/iam.tf) — cluster, node, backend_irsa,
        # alb_controller_irsa. AttachRolePolicy/DetachRolePolicy needed here (not just
        # PutRolePolicy/DeleteRolePolicy) because eks_cluster/eks_node use AWS-managed-policy
        # attachments, not inline policies — a real difference from cd_lambda_deploy/
        # cd_ecs_deploy's execution roles, which only ever use aws_iam_role_policy.
        Effect = "Allow"
        Action = [
          "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
          "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
          "iam:TagRole", "iam:ListRoleTags", "iam:PassRole", "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        ]
        Resource = [
          "arn:aws:iam::*:role/crag-prod-eks-cluster",
          "arn:aws:iam::*:role/crag-prod-eks-node",
          "arn:aws:iam::*:role/crag-prod-eks-backend-irsa",
          "arn:aws:iam::*:role/crag-prod-eks-alb-controller-irsa",
        ]
      },
      {
        # This stack's own OIDC provider (infra/eks/iam.tf's aws_iam_openid_connect_provider.eks,
        # federating the cluster's IRSA issuer) — distinct from this file's own GitHub Actions
        # OIDC provider above, which cd-eks.yml never needs to touch.
        Effect   = "Allow"
        Action   = ["iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider", "iam:GetOpenIDConnectProvider", "iam:TagOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags", "iam:UpdateOpenIDConnectProviderThumbprint"]
        Resource = "*" # no resource-level restriction possible before the provider exists / on GetOpenIDConnectProvider's ARN-per-issuer shape
      },
      {
        # First-time-in-account only, same reasoning/no-op-after-first as cd_ecs_deploy's
        # identical grant — EKS needs its own service-linked role too.
        Effect   = "Allow"
        Action   = ["iam:CreateServiceLinkedRole"]
        Resource = "arn:aws:iam::*:role/aws-service-role/*"
      },
    ]
  })
}
