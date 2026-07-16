variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "localstack"
}

# Flips every LocalStack-only provider setting in providers.tf. Set to false
# (-var="use_localstack=false") once this same config is re-pointed at real AWS.
variable "use_localstack" {
  type    = bool
  default = true
}

# Same project/environment defaults as infra/lambda-gate/ and infra/fargate/, but this module
# never reads or references either module's state, resources, or SSM parameters — its own ECR
# repo (ecr.tf), SSM secrets (ssm.tf), and every other resource are entirely independent. Resource
# names that must be unique across all three stacks (ECR repo, VPC, EKS cluster/node group, SSM
# path) get an explicit "-eks" component (local.name_prefix / local.ssm_prefix, network.tf) so
# they never collide with the other two stacks' same-named resources.
variable "project_name" {
  type    = string
  default = "crag"
}

variable "environment" {
  type    = string
  default = "prod"
}

# Tag deployed by `helm upgrade --set image.tag=...` (or, once Phase 21 exists, by cd-eks.yml
# committing this same value into gitops/multi-agent/values.yaml) — not read by this stack's own
# Terraform at all, since the container image is deployed via Helm, not baked into an
# aws_eks_node_group or aws_eks_cluster resource the way Lambda/ECS bake it into their own
# compute resource. Kept here only so ecr.tf's repository and this variable live next to each
# other for discoverability; the default is never actually applied by this module.
variable "backend_image_tag" {
  type    = string
  default = "latest"
}

# Every secret backend/config.py's _SSM_SECRET_KEYS expects, same as infra/lambda-gate/'s and
# infra/fargate/'s var.secrets — populated from this stack's own infra/eks/secrets.auto.tfvars
# (gitignored), a deliberate duplicate of the other two stacks' secrets.auto.tfvars kept in sync
# by hand (see ssm.tf).
variable "secrets" {
  type      = map(string)
  sensitive = true
}

# LocalStack Ultimate's EKS emulation doesn't track real AWS's supported-version list 1:1 — a
# real gap found on the first apply here: 1.29 (this repo's other, older EKS-version assumption)
# was rejected outright with InvalidParameterException, discovered via
# `aws eks describe-addon-versions --addon-name vpc-cni --endpoint-url http://localhost:4566
# --query 'addons[0].addonVersions[0].compatibilities[].clusterVersion'`, which enumerated
# 1.30-1.36 as the actual supported range on this LocalStack build (2026.7.0.dev195). Re-check
# that command if this default ever fails the same way again — LocalStack's supported range
# shifts across its own releases, independent of what real AWS supports at the same time.
variable "cluster_version" {
  type    = string
  default = "1.31"
}

# Smallest instance type AWS's own EKS-optimized AMI realistically runs on with room left for
# the kubelet/CNI/kube-proxy daemonset overhead alongside actual pods — t3.small technically
# boots but leaves very little allocatable capacity. Still one size class above Phase 16's
# Fargate task (0.25 vCPU / 0.5 GB, variables.tf there) since a node has to carry cluster
# system pods on top of the app, not just the app itself.
variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

# One node by default, matching plan.md step 2's "desired size 1-2" — bump desired (and max, if
# needed) rather than min when testing the HPA/node-scaling story; keeping min at 1 is what makes
# `terraform destroy` between demos (step 10) actually tear the node group down to nothing rather
# than something reconciling it back up.
variable "node_desired_size" {
  type    = number
  default = 1
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_max_size" {
  type    = number
  default = 2
}

# Must exactly match gitops/multi-agent/templates/serviceaccount.yaml's
# `metadata.name`/`metadata.namespace` once that chart exists (Phase 20 step 3) — this is the
# other half of the trust-policy Condition in iam.tf's aws_iam_role.backend_irsa. Getting this
# wrong doesn't fail Terraform; it fails silently at pod-startup time (the pod's assumed role
# won't match what AWS actually issued a token for), so it's called out here rather than left to
# be discovered only once the chart is written.
variable "backend_service_account" {
  type    = string
  default = "default:backend"
}

variable "log_retention_days" {
  type    = number
  default = 14
}
