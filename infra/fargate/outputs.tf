output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

# The finish line — the app's public URL, per plan.md Phase 16.
output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.this.domain_name
}
