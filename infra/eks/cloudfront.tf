# Simplified from infra/lambda-gate/cloudfront.tf's shape, same reasoning infra/fargate/'s copy
# of this file gives: a real backend container behind a real ALB streams StreamingResponse/SSE
# natively, so there's no Function-URL-vs-API-Gateway split to route around — one ALB origin
# handles every /v1/* route, streaming or not.
#
# One real difference from infra/fargate/cloudfront.tf: that stack's ALB is a Terraform resource
# (aws_lb.this, alb.tf) it created itself. This stack's ALB is Kubernetes-managed — created by the
# AWS Load Balancer Controller reconciling gitops/multi-agent/templates/ingress.yaml, entirely
# outside this Terraform state. So instead of referencing a resource, the origin below looks the
# real ALB up by the tags the controller itself sets on it (confirmed via `aws elbv2 describe-tags`
# against the real ALB: elbv2.k8s.aws/cluster=<cluster_name>, ingress.k8s.aws/stack=<namespace>/
# <ingress-name>) — this is also why this file has no LocalStack validation at all: the ALB
# Controller never reconciles on LocalStack's EKS emulation (a confirmed gap, see iam.tf's history
# of this stack), so there is no ALB for this data source to find there. Real AWS only.
data "aws_lb" "backend" {
  tags = {
    "elbv2.k8s.aws/cluster" = local.name_prefix
    "ingress.k8s.aws/stack" = "default/multi-agent-backend"
  }
}

resource "aws_cloudfront_origin_access_control" "s3_oac" {
  name                              = "${local.name_prefix}-s3-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_cache_policy" "static_assets" {
  name        = "${local.name_prefix}-static-assets"
  min_ttl     = 1
  default_ttl = 86400
  max_ttl     = 31536000

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# Every /v1/* call is a live backend call — nothing here is ever cacheable, same as
# infra/lambda-gate/cloudfront.tf's and infra/fargate/cloudfront.tf's no_cache policy.
resource "aws_cloudfront_cache_policy" "no_cache" {
  name        = "${local.name_prefix}-no-cache"
  min_ttl     = 0
  default_ttl = 0
  max_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = false
    enable_accept_encoding_brotli = false

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# "allExcept: Host" — the ALB origin needs CloudFront to set Host itself to match the ALB's own
# domain; forwarding the viewer's original Host would mismatch what the ALB/target group expect.
resource "aws_cloudfront_origin_request_policy" "forward_all_except_host" {
  name = "${local.name_prefix}-forward-all-except-host"

  cookies_config {
    cookie_behavior = "all"
  }
  headers_config {
    header_behavior = "allExcept"
    headers {
      items = ["Host"]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

# Same CloudFront Function as infra/lambda-gate/cloudfront.tf and infra/fargate/cloudfront.tf —
# Next.js's static export needs extensionless URLs (/login) rewritten to their on-disk file
# (/login.html) before reaching S3.
resource "aws_cloudfront_function" "url_rewrite" {
  name    = "${local.name_prefix}-url-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Appends .html / index.html to extensionless URIs for the Next.js static export"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      if (uri.includes('.')) {
        return request;
      }

      request.uri = uri.endsWith('/') ? uri + 'index.html' : uri + '.html';
      return request;
    }
  EOT
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = local.name_prefix
  price_class         = "PriceClass_100"

  origin {
    origin_id                = "s3-frontend"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.s3_oac.id
  }

  # No OAC here — an ALB has no resource-policy equivalent to sign against (same reasoning
  # infra/lambda-gate/cloudfront.tf and infra/fargate/cloudfront.tf give for their own non-S3
  # origins). HTTP only — no ACM cert obtainable without a custom domain, which this phase has
  # none of, same as every other deploy target in this plan.
  origin {
    origin_id   = "alb"
    domain_name = data.aws_lb.backend.dns_name

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]

      # Matches infra/fargate/cloudfront.tf's identical reasoning: the CRAG pipeline's own
      # measured worst-case latency (a multi-step web-search + LLM chain) can run well past
      # CloudFront's 30s origin_read_timeout default.
      origin_read_timeout = 60
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = aws_cloudfront_cache_policy.static_assets.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.url_rewrite.arn
    }
  }

  # One behavior for all of /v1/* — streaming and non-streaming routes alike — matching
  # infra/fargate/cloudfront.tf's reasoning: the ALB-fronted pod handles both natively.
  ordered_cache_behavior {
    path_pattern             = "/v1/*"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.no_cache.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.forward_all_except_host.id
  }

  # api/main.py mounts /health deliberately outside the /v1 prefix, so it never matches the
  # /v1/* behavior above and would otherwise fall through to the S3 frontend origin's
  # default_cache_behavior — a 404 NoSuchKey, not a real health-check failure. Same gap
  # infra/lambda-gate/cloudfront.tf and infra/fargate/cloudfront.tf both already document/fix.
  ordered_cache_behavior {
    path_pattern             = "/health"
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = aws_cloudfront_cache_policy.no_cache.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.forward_all_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # No custom domain this phase (plan.md) — the default *.cloudfront.net cert is all that's
  # needed/available.
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
