# Private bucket behind CloudFront's s3_oac (cloudfront.tf) — no website hosting, no public
# access. Next.js static export (frontend/out/, built + pushed by
# infra/scripts/sync_frontend.sh) is the only thing that ever lands here.
resource "aws_s3_bucket" "frontend" {
  bucket        = "${var.project_name}-${var.environment}-frontend"
  force_destroy = var.use_localstack
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Condition.StringEquals on the distribution's own ARN (not just "any CloudFront service
# principal") — the standard OAC bucket-policy shape, so no other AWS account's CloudFront
# distribution could read this bucket even if it somehow guessed the bucket name.
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipalReadOnly"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this.arn
        }
      }
    }]
  })
}
