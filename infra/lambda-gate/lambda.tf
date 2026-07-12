# Comment-only touch (2026-07-12): no resource change. infra/lambda-gate/** needed a real diff
# so cd-lambda.yml's paths-filter step would take its terraform-apply path on the first-ever run
# against a from-scratch LocalStack instance (there is no existing function for the fast
# update-function-code path to target yet) — see completed.md's Phase 18 CD-verification entry.
# dorny/paths-filter diffs only the latest commit here (no push before/after context on a
# workflow_call trigger), so this file needs re-touching alongside each cd-lambda.yml fix commit
# during this same verification pass, until the first full apply actually lands. (iteration 2:
# added TF_VAR_secrets, sourced from a new LOCALSTACK_SECRETS_JSON repo Secret.)
locals {
  function_name        = "${var.project_name}-${var.environment}-backend"
  stream_function_name = "${var.project_name}-${var.environment}-backend-stream"

  # Shared by both functions — same image, same runtime concerns, only AWS_LWA_INVOKE_MODE
  # differs between them (added separately below).
  common_env = {
    APP_ENV              = "production"
    SSM_PARAMETER_PREFIX = "/${var.project_name}/${var.environment}"
    # Lambda's root filesystem is read-only outside /tmp — multi_agent/ingestion.py copies its
    # image-baked Chroma collection here on cold start when this is set (no-op everywhere else,
    # including Docker Compose, which bind-mounts the real directory instead). Found by actually
    # invoking the function against LocalStack: PermissionError writing to
    # /app/multi_agent/.chroma (Phase 15 Stage B).
    CHROMA_PERSIST_DIR = "/tmp/chroma"
  }
}

# Created explicitly (and referenced via depends_on below) so Lambda doesn't fall back to
# auto-creating its own log group with infinite retention.
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "backend_stream" {
  name              = "/aws/lambda/${local.stream_function_name}"
  retention_in_days = var.log_retention_days
}

# Buffered function — fronted only by API Gateway (apigateway.tf). AWS_LWA_INVOKE_MODE is
# deliberately unset (defaults to the adapter's own buffered mode): API Gateway's HTTP API
# integration always uses a classic buffered Invoke, never InvokeWithResponseStream, and cannot
# parse the adapter's streaming-format output (a JSON prelude + 8 null bytes + body) — confirmed
# by actually invoking a single shared function through LocalStack's API Gateway emulation and
# seeing exactly that malformed body (Phase 15 Stage B). Split into two functions from the same
# image rather than trying to make one function serve both invoke shapes.
resource "aws_lambda_function" "backend" {
  function_name = local.function_name
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

  # 29s is API Gateway's own integration timeout — 60s here is headroom under that, not a promise
  # that API-Gateway-routed calls can run longer than API Gateway itself allows.
  timeout     = 60
  memory_size = 1024

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.backend]
}

# Streaming function — same image, fronted only by the Function URL below. RESPONSE_STREAM here
# sidesteps API Gateway's 29s timeout/response buffering for the chat/stream routes specifically
# (enterprize-deploy-steps.md's architecture) — this function is never invoked via API Gateway,
# so its streaming-shaped output is never seen by anything that can't parse it.
resource "aws_lambda_function" "backend_stream" {
  function_name = local.stream_function_name
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

  timeout     = 60
  memory_size = 1024

  environment {
    variables = merge(local.common_env, {
      AWS_LWA_INVOKE_MODE = "RESPONSE_STREAM"
    })
  }

  depends_on = [aws_cloudwatch_log_group.backend_stream]
}

# AWS_IAM, not NONE — CloudFront's Origin Access Control signs requests to it (see the
# CloudFront-side aws_lambda_permission in cloudfront.tf, added once the distribution exists).
resource "aws_lambda_function_url" "backend_stream" {
  function_name      = aws_lambda_function.backend_stream.function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "RESPONSE_STREAM"
}

# Resource-based policy, not an IAM role — this, not anything on lambda_exec, is what actually
# lets API Gateway invoke the function.
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
