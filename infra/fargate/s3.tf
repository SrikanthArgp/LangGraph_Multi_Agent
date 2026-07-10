# A separate bucket from infra/lambda-gate/s3.tf's aws_s3_bucket.frontend, not the same one
# reused — this is a distinct Terraform root with its own state, and two roots can't manage the
# same S3 bucket resource. Same Next.js static export (frontend/out/) gets synced here too, via
# this stack's own infra/fargate/scripts/sync_frontend.sh.
resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.name_prefix}-frontend"
  force_destroy = var.use_localstack
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

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
