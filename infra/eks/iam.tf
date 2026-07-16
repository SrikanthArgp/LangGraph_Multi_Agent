# Four distinct IAM roles in this file, each serving a different EKS-specific principal — no
# overlap with infra/fargate/iam.tf's two-role (execution/task) split:
#   1. eks_cluster        — assumed by the EKS *service* itself, to manage the control plane's own
#                            ENIs/security groups on your behalf.
#   2. eks_node            — assumed by every EC2 instance in the node group, for the
#                            kubelet/CNI/ECR pull machinery every node needs regardless of which
#                            pods land on it.
#   3. backend_irsa        — assumed by the backend *pod* specifically (via IRSA), for the same
#                            "read this stack's own SSM secrets" job infra/fargate/iam.tf's
#                            ecs_task role does — scoped per-ServiceAccount, not inherited by
#                            every pod on the node the way a node-level role would be.
#   4. alb_controller_irsa — assumed via IRSA by the AWS Load Balancer Controller's own
#                            ServiceAccount (kube-system:aws-load-balancer-controller) once that
#                            controller is helm-installed (plan.md step 4, its own Helm chart —
#                            eks/aws-load-balancer-controller — not gitops/multi-agent/). This
#                            role is cluster infrastructure, not app-level, which is why it lives
#                            here in Terraform rather than being defined by that Helm chart itself
#                            — same "Terraform owns IAM, Helm owns app pods" split backend_irsa
#                            already draws.

# ---------------------------------------------------------------------------
# 1. Cluster role — assumed by eks.amazonaws.com.
# ---------------------------------------------------------------------------
# AWS-managed policy, not a narrow inline one — a deliberate exception to this repo's usual
# "self-documenting inline policy" convention (infra/fargate/iam.tf's header comment). Unlike an
# ECS execution role, EKS's control plane needs a wide, AWS-defined set of EC2/ELB permissions to
# manage cluster networking on your behalf, and that set isn't meaningfully narrower to hand-roll
# — it's the standard AWS-documented requirement for any EKS cluster, LocalStack or real.
resource "aws_iam_role" "eks_cluster" {
  name = "${local.name_prefix}-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ---------------------------------------------------------------------------
# 2. Node role — assumed by every EC2 instance in aws_eks_node_group.this (eks.tf).
# ---------------------------------------------------------------------------
# Same "AWS-managed, not inline" exception as the cluster role above, for the same reason: these
# three policies are the standard, AWS-documented minimum for any EKS-optimized AMI node to join
# a cluster and run pods at all (kubelet<->control-plane auth, the VPC CNI's ENI/IP management,
# and pulling images — including this app's own, via ecr.tf — from ECR).
resource "aws_iam_role" "eks_node" {
  name = "${local.name_prefix}-node"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_node_worker" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_ecr" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ---------------------------------------------------------------------------
# IRSA plumbing — lets a specific Kubernetes ServiceAccount (not every pod on the node) assume a
# specific IAM role, by federating the cluster's own OIDC issuer as an IAM identity provider.
# Created from the cluster's real issuer URL, so this resource can't exist until
# aws_eks_cluster.this does.
# ---------------------------------------------------------------------------
data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]

  # Real gap found on this stack's first post-create plan: LocalStack's read-back normalizes
  # this attribute by stripping the https:// scheme (state ends up
  # "localhost.localstack.cloud:4510" against a config value of
  # "https://localhost.localstack.cloud:4510"), which Terraform treats as a ForceNew diff —
  # every subsequent plan wants to destroy and recreate this resource for no semantic reason
  # (the ARN, which is what every IRSA trust policy in this file actually references, is
  # scheme-independent and doesn't change). Ignored here rather than "fixed" by stripping
  # https:// from the config value, since the argument is documented as requiring the full URL
  # with scheme at create time.
  lifecycle {
    ignore_changes = [url]
  }
}

locals {
  # aws_iam_openid_connect_provider.eks.url is the issuer with its https:// prefix stripped —
  # IAM's own condition-key convention (the same shape infra/bootstrap/github-oidc.tf's
  # token.actions.githubusercontent.com:sub key uses for GitHub's OIDC provider), needed
  # verbatim in the Condition block below.
  oidc_issuer_host = replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
}

# ---------------------------------------------------------------------------
# 3. Backend pod role — assumed via IRSA by whichever ServiceAccount
# var.backend_service_account names (gitops/multi-agent/templates/serviceaccount.yaml, once that
# chart exists — Phase 20 step 3). Same SSM-read job infra/fargate/iam.tf's ecs_task role does,
# just federated through the cluster's OIDC provider instead of being attached directly to a
# task definition.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "backend_irsa" {
  name = "${local.name_prefix}-backend-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_issuer_host}:aud" = "sts.amazonaws.com"
          "${local.oidc_issuer_host}:sub" = "system:serviceaccount:${var.backend_service_account}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "backend_irsa_ssm" {
  name = "ssm"
  role = aws_iam_role.backend_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParametersByPath",
      ]
      Resource = "arn:aws:ssm:*:*:parameter${local.ssm_prefix}/*"
    }]
  })
}

# Same KMS gotcha infra/lambda-gate/iam.tf and infra/fargate/iam.tf both document: ssm:GetParameter
# alone isn't enough for SecureString params, SSM makes a KMS Decrypt call under the caller's
# (here: the assumed IRSA role's) identity.
resource "aws_iam_role_policy" "backend_irsa_kms" {
  name = "kms"
  role = aws_iam_role.backend_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "kms:Decrypt"
      Resource = "arn:aws:kms:*:*:alias/aws/ssm"
    }]
  })
}

# ---------------------------------------------------------------------------
# 4. AWS Load Balancer Controller role — assumed via IRSA by
# kube-system:aws-load-balancer-controller once that controller is installed (plan.md step 4).
# Trust condition follows the exact same shape as backend_irsa's above, just a different
# ServiceAccount identity — the controller's own Helm chart creates that ServiceAccount (with
# this role's ARN as its eks.amazonaws.com/role-arn annotation, passed via
# --set serviceAccount.annotations at install time), gitops/multi-agent/ has nothing to do with
# this one.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "alb_controller_irsa" {
  name = "${local.name_prefix}-alb-controller-irsa"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_issuer_host}:aud" = "sts.amazonaws.com"
          "${local.oidc_issuer_host}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }
      }
    }]
  })
}

# Read via file(), not hand-transcribed into jsonencode({...}) — this is the verbatim upstream
# policy (infra/eks/policies/aws_load_balancer_controller_iam_policy.json, fetched from
# kubernetes-sigs/aws-load-balancer-controller's docs/install/iam_policy.json), ~250 lines and
# maintained by that project, not this one. Transcribing it into HCL risks a silent typo in a
# policy this repo doesn't own the correctness of; referencing the file directly means picking up
# upstream's own file verbatim if it's ever refreshed.
resource "aws_iam_role_policy" "alb_controller_irsa" {
  name   = "controller"
  role   = aws_iam_role.alb_controller_irsa.id
  policy = file("${path.module}/policies/aws_load_balancer_controller_iam_policy.json")
}
