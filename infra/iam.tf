# Deliberately three narrow inline policies instead of the AWS-managed
# AWSLambdaBasicExecutionRole, so the role stays self-documenting (enterprize-deploy-steps.md's
# "Resource Wiring Detail" section).
resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-${var.environment}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_logs" {
  name = "logs"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      # Trailing `*` (not a literal ":*") so this one statement covers both the buffered
      # "...-backend" and streaming "...-backend-stream" log groups (lambda.tf) — both functions
      # share this role rather than getting their own.
      Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/${var.project_name}-${var.environment}-backend*:*"
    }]
  })
}

# Read-only — the function never writes secrets, only reads them at cold start
# (config.py's bootstrap_env()).
resource "aws_iam_role_policy" "lambda_ssm" {
  name = "ssm"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParametersByPath",
      ]
      Resource = "arn:aws:ssm:*:*:parameter/${var.project_name}/${var.environment}/*"
    }]
  })
}

# Easy to miss: ssm:GetParameter alone isn't enough for SecureString params — SSM makes a KMS
# Decrypt call under the caller's identity. Without this the function 403s on every secret read
# at runtime, not at `terraform apply` time. No customer-managed key needed at this scale —
# alias/aws/ssm is the default AWS-managed key SSM uses for SecureString by default.
resource "aws_iam_role_policy" "lambda_kms" {
  name = "kms"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "kms:Decrypt"
      Resource = "arn:aws:kms:*:*:alias/aws/ssm"
    }]
  })
}
