# Own repository, not a reference to infra/lambda-gate/ecr.tf's — this stack doesn't depend on
# anything in infra/lambda-gate/ at any layer (Terraform state, runtime SSM reads, or tooling
# scripts), the entire reason it's a separate folder in the first place. Same underlying image
# works unchanged here too (backend/Dockerfile's Lambda Web Adapter layer is documented there as
# inert outside Lambda), just built and pushed independently via
# infra/fargate/scripts/push_image.sh.
resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  force_delete = var.use_localstack
}
