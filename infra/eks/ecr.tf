# Own repository, not a reference to infra/lambda-gate's or infra/fargate's — same independence
# rationale as infra/fargate/ecr.tf's identical comment: this stack doesn't depend on either
# other stack at any layer. Same underlying backend/Dockerfile image works unchanged here too
# (its Lambda Web Adapter layer is documented there as inert outside Lambda); node pulls happen
# via the node role's AmazonEC2ContainerRegistryReadOnly attachment (iam.tf), so — unlike Lambda —
# no aws_ecr_repository_policy resource-based grant is needed on the repository itself.
resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  force_delete = var.use_localstack
}
