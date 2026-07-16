#!/usr/bin/env bash
# Builds backend/Dockerfile and pushes it to this stack's own ECR repo (infra/eks/ecr.tf's
# aws_ecr_repository.backend — a separate repository from infra/lambda-gate/ecr.tf's and
# infra/fargate/ecr.tf's, not shared, per this whole folder's point of not depending on either
# other stack at any layer). Same image works unchanged here — the Lambda Web Adapter layer it
# carries is documented in backend/Dockerfile as inert outside Lambda (nothing invokes the
# Runtime Interface Client under plain `docker run`/ECS/a Kubernetes pod).
#
# Same LocalStack ECR quirk infra/fargate/scripts/push_image.sh documents: a plain
# `docker push localhost:4566/...` does NOT work — ECR is a real Docker Registry v2 API, not a
# generic REST endpoint. LocalStack answers on a wildcard hostname pattern,
# `<registry-id>.dkr.ecr.<region>.localhost.localstack.cloud:4566`, resolving to 127.0.0.1 via
# LocalStack's public `*.localstack.cloud` DNS.
#
# Usage: infra/eks/scripts/push_image.sh [image-tag]   (default tag: latest, matches
#   var.backend_image_tag's default in infra/eks/variables.tf — this stack's Terraform never
#   reads that variable though, since the image is deployed via `helm install`/`helm upgrade`,
#   not baked into an aws_eks_node_group/aws_eks_cluster resource — pass a new tag here, then
#   `helm upgrade multi-agent gitops/multi-agent --set image.tag=<tag>` to actually roll it out.)
set -euo pipefail

TAG="${1:-latest}"
AWS_REGION="us-east-1"
ENDPOINT_URL="http://localhost:4566"
REPO_NAME="crag-prod-eks-backend"

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
