#!/usr/bin/env bash
# Syncs frontend/out/ (the Next.js static export) to this stack's own S3 bucket
# (infra/eks/s3.tf's aws_s3_bucket.frontend — a separate bucket from infra/lambda-gate/s3.tf's and
# infra/fargate/s3.tf's, not shared). Mirrors those two stacks' sync_frontend.sh pattern:
# Terraform provisions the bucket, this script is the separate manual step that populates it.
#
# Must be built with NEXT_OUTPUT_MODE=export and NEXT_PUBLIC_API_BASE_URL=/v1 — the latter is a
# same-origin relative path (not an absolute ALB/localhost URL) so the built JS calls whatever
# host actually serves the page, letting CloudFront's own path-based routing (/v1/* -> the ALB,
# cloudfront.tf) do the rest.
#
# Real AWS only — no LocalStack variant, since this stack's ALB is Kubernetes-managed and never
# gets created on LocalStack's EKS emulation (a confirmed gap, see cloudfront.tf's data.aws_lb
# comment), so there is nothing for infra/eks's CloudFront distribution to point at there.
#
# Usage: infra/eks/scripts/sync_frontend.sh
set -euo pipefail

AWS_REGION="us-east-1"
FRONTEND_DIR="$(dirname "$0")/../../../frontend"

if [ ! -d "$FRONTEND_DIR/out" ]; then
  echo "no $FRONTEND_DIR/out - run: NEXT_OUTPUT_MODE=export NEXT_PUBLIC_API_BASE_URL=/v1 npm run build (from frontend/)" >&2
  exit 1
fi

BUCKET=$(cd "$(dirname "$0")/.." && terraform output -raw frontend_bucket_name)

echo "Syncing $FRONTEND_DIR/out to s3://$BUCKET ..."
aws s3 sync "$FRONTEND_DIR/out" "s3://$BUCKET" \
  --region "$AWS_REGION" \
  --delete

echo "Done."
