#!/usr/bin/env bash
# Syncs frontend/out/ (the Next.js static export, see enterprize-deploy-steps.md Stage A step 5)
# to the S3 bucket Terraform provisioned (infra/s3.tf's aws_s3_bucket.frontend). Mirrors
# push_image.sh's pattern for the backend image: Terraform provisions the bucket, this script
# is the separate manual/CI step that actually populates it.
#
# Must be built with NEXT_OUTPUT_MODE=export and NEXT_PUBLIC_API_BASE_URL=/v1 — the latter is a
# same-origin relative path (not an absolute localhost:8000 URL) so the built JS calls whatever
# host actually serves the page, letting CloudFront's own path-based routing
# (/v1/* -> API Gateway or the streaming Function URL, cloudfront.tf) do the rest.
#
# Usage: infra/scripts/sync_frontend.sh
set -euo pipefail

AWS_REGION="us-east-1"
ENDPOINT_URL="http://localhost:4566"
FRONTEND_DIR="$(dirname "$0")/../../frontend"

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"

BUCKET=$(cd "$(dirname "$0")/.." && terraform output -raw frontend_bucket_name)

if [ ! -d "$FRONTEND_DIR/out" ]; then
  echo "no $FRONTEND_DIR/out - run: NEXT_OUTPUT_MODE=export NEXT_PUBLIC_API_BASE_URL=/v1 npm run build (from frontend/)" >&2
  exit 1
fi

echo "Syncing $FRONTEND_DIR/out to s3://$BUCKET ..."
aws s3 sync "$FRONTEND_DIR/out" "s3://$BUCKET" \
  --region "$AWS_REGION" \
  --endpoint-url "$ENDPOINT_URL" \
  --delete

echo "Done."
