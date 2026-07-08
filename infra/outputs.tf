output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "function_url" {
  value = aws_lambda_function_url.backend_stream.function_url
}

output "api_endpoint" {
  value = aws_apigatewayv2_stage.default.invoke_url
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

# The finish line — the app's public URL, per enterprize-deploy-steps.md's wiring table.
output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.this.domain_name
}
