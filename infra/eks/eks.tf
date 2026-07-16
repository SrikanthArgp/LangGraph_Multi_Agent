# The cluster itself — the control plane AWS runs and bills at a flat ~$0.10/hr regardless of
# usage (plan.md step 10, Cost Profile Summary). endpoint_public_access = true, no
# endpoint_private_access: this is a learning deployment with no VPN/Direct Connect back to a
# private network, so kubectl/helm from a local dev machine need the public endpoint — matching
# this whole plan's existing "no NAT Gateway, no private-subnet-only resource" pattern for
# anything that doesn't strictly require one.
resource "aws_eks_cluster" "this" {
  name     = local.name_prefix
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_public_access  = true
    endpoint_private_access = false
  }

  # Terraform re-asserts this attachment on every apply regardless, but an explicit depends_on
  # documents (and, on the very first apply, actually enforces) that the role must have its
  # managed policy attached before EKS will accept it as this cluster's role_arn — matching
  # infra/fargate/ecs.tf's same "first apply only" category of ordering requirement.
  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]

  tags = { Name = local.name_prefix }
}

# One managed node group — AWS handles the EC2 instances' lifecycle (launch, drain-and-replace on
# scaling/AMI updates) rather than this stack hand-rolling an aws_autoscaling_group + launch
# template the way a "self-managed" node group would. desired/min/max sizes are all
# variables.tf-driven (plan.md step 2's "desired size 1-2").
resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${local.name_prefix}-nodes"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = aws_subnet.public[*].id

  instance_types = [var.node_instance_type]
  capacity_type  = "ON_DEMAND"

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  # Same reasoning as eks_cluster_policy's depends_on above — the node IAM role needs all three
  # managed policies attached before EKS will let its instances actually join the cluster, not
  # just before Terraform considers the role "created".
  depends_on = [
    aws_iam_role_policy_attachment.eks_node_worker,
    aws_iam_role_policy_attachment.eks_node_cni,
    aws_iam_role_policy_attachment.eks_node_ecr,
  ]

  tags = { Name = "${local.name_prefix}-nodes" }
}
