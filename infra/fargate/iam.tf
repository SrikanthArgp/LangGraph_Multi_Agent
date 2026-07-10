# Two roles, not one — the standard ECS split. The execution role is what the ECS agent itself
# assumes to pull the image and set up logging *before* the container starts; the task role is
# what the running application code assumes, same as infra/lambda-gate/iam.tf's lambda_exec role
# plays for the Lambda functions. Narrow inline policies on both, not the AWS-managed
# AmazonECSTaskExecutionRolePolicy, matching infra/lambda-gate/iam.tf's same "self-documenting
# role" reasoning.

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name_prefix}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# ECR pull needs GetAuthorizationToken (account-wide — ECR's auth API has no per-repository
# scoping) plus the two per-repository actions the agent calls once authenticated.
resource "aws_iam_role_policy" "ecs_execution_ecr" {
  name = "ecr"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = aws_ecr_repository.backend.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_execution_logs" {
  name = "logs"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.backend.arn}:*"
    }]
  })
}

# The running application's role — reads this stack's own SSM secrets (ssm.tf, local.ssm_prefix)
# via the exact same config.py bootstrap_env() code path Lambda uses (APP_ENV=production +
# SSM_PARAMETER_PREFIX, set in ecs.tf's container definition), just pointed at this stack's own
# parameter path rather than infra/lambda-gate/'s.
resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_ssm" {
  name = "ssm"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParametersByPath",
      ]
      Resource = "arn:aws:ssm:*:*:parameter${local.ssm_prefix}/*"
    }]
  })
}

# Same KMS gotcha infra/lambda-gate/iam.tf's lambda_kms policy documents: ssm:GetParameter alone
# isn't enough for SecureString params, SSM makes a KMS Decrypt call under the caller's identity.
resource "aws_iam_role_policy" "ecs_task_kms" {
  name = "kms"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "kms:Decrypt"
      Resource = "arn:aws:kms:*:*:alias/aws/ssm"
    }]
  })
}
