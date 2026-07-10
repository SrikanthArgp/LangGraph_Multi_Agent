#!/usr/bin/env bash
# Builds backend/Dockerfile and pushes it to this stack's own ECR repo (infra/fargate/ecr.tf's
# aws_ecr_repository.backend — a separate repository from infra/lambda-gate/ecr.tf's, not shared,
# per this whole folder's point of not depending on infra/lambda-gate/ at any layer). Same image
# works unchanged here — the Lambda Web Adapter layer it carries is documented in
# backend/Dockerfile as inert outside Lambda (nothing invokes the Runtime Interface Client under
# plain `docker run`/ECS).
#
# LocalStack quirk, verified empirically against LocalStack Ultimate (a plain
# `docker push localhost:4566/...` does NOT work — ECR is a real Docker Registry v2 API, not a
# generic REST endpoint like the other LocalStack-emulated services): LocalStack answers on a
# wildcard hostname pattern, `<registry-id>.dkr.ecr.<region>.localhost.localstack.cloud:4566`,
# which resolves to 127.0.0.1 via LocalStack's public `*.localstack.cloud` DNS. Real AWS ECR uses
# the same repository_uri shape, just on the real `amazonaws.com` domain — so nothing here is
# LocalStack-only except the endpoint host itself.
#
# Usage: infra/fargate/scripts/push_image.sh [image-tag]   (default tag: latest, matches
#   var.backend_image_tag's default in infra/fargate/variables.tf — pass a new tag and re-run
#   `tflocal apply -var="backend_image_tag=<tag>"` to roll out a new image)
set -euo pipefail

TAG="${1:-latest}"
AWS_REGION="us-east-1"
ENDPOINT_URL="http://localhost:4566"
REPO_NAME="crag-prod-ecs-backend"

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"

REPO_URI=$(aws ecr describe-repositories \
  --repository-names "$REPO_NAME" \
  --region "$AWS_REGION" \
  --endpoint-url "$ENDPOINT_URL" \
  --query 'repositories[0].repositoryUri' \
  --output text)

echo "Building backend image..."
docker build -t "$REPO_NAME:$TAG" "$(dirname "$0")/../../../backend"

echo "Tagging as $REPO_URI:$TAG"
docker tag "$REPO_NAME:$TAG" "$REPO_URI:$TAG"

echo "Logging in to $REPO_URI"
aws ecr get-login-password --region "$AWS_REGION" --endpoint-url "$ENDPOINT_URL" \
  | docker login --username AWS --password-stdin "$REPO_URI"

echo "Pushing..."
docker push "$REPO_URI:$TAG"

echo "Done. image_uri = $REPO_URI:$TAG"
