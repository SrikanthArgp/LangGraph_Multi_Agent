output "cluster_name" {
  value = aws_eks_cluster.this.name
}

# Feed this straight to `aws eks update-kubeconfig --name <cluster_name> --region <region>` (add
# --endpoint-url http://localhost:4566 for LocalStack, same pattern as every other aws-cli call
# against this stack) — that command is what actually populates kubectl's config with this URL,
# so the output exists for visibility/debugging, not because anything reads it directly.
output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

# The role gitops/multi-agent/templates/serviceaccount.yaml's
# `eks.amazonaws.com/role-arn` annotation must reference, once that chart exists — this is the
# Terraform-to-Helm handoff point for IRSA (iam.tf's backend_irsa role, federated via
# aws_iam_openid_connect_provider.eks).
output "backend_irsa_role_arn" {
  value = aws_iam_role.backend_irsa.arn
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.eks.arn
}

# Feed this straight to the controller's own Helm chart at install time:
#   helm install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system \
#     --set clusterName=$(terraform output -raw cluster_name) \
#     --set serviceAccount.name=aws-load-balancer-controller \
#     --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$(terraform output -raw alb_controller_irsa_role_arn)
output "alb_controller_irsa_role_arn" {
  value = aws_iam_role.alb_controller_irsa.arn
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

# The finish line — the app's public URL, per plan.md Phase 20's "run the same manual smoke test
# as Phases 15-16" step. Requires data.aws_lb.backend (cloudfront.tf) to actually resolve, which
# means the Ingress must already have a real ADDRESS (i.e. the AWS Load Balancer Controller must
# already have reconciled it) before this stack's first apply — a real ordering dependency this
# stack has that Phases 15/16 don't, since their ALB/API Gateway are Terraform-managed and this
# one is Kubernetes-managed.
output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.this.domain_name
}
