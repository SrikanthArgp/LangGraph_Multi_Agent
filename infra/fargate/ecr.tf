# Own repository, not a reference to infra/lambda-gate/ecr.tf's — this stack doesn't depend on
# anything in infra/lambda-gate/ at any layer (Terraform state, runtime SSM reads, or tooling
# scripts), the entire reason it's a separate folder in the first place. Same underlying image
# works unchanged here too (backend/Dockerfile's Lambda Web Adapter layer is documented there as
# inert outside Lambda), just built and pushed independently — via cd-ecs.yml's own inline
# build-and-push step during a real CD run, not infra/fargate/scripts/push_image.sh, which is
# leftover manual-deploy tooling from before CD existed. See infra/lambda-gate/ecr.tf's identical
# comment on why a reset LocalStack instance should be recovered through a real CD run (diff
# touching this directory) rather than by hand.
#
# Same paths-filter single-commit-diff gap documented in infra/lambda-gate/ecr.tf's identical
# comment, hit here on this stack's first real-AWS dispatch: the prior commit didn't touch
# infra/fargate/**, so cd-ecs.yml took the fast (image-only) path against a stack that had never
# been applied, and failed pushing to a nonexistent ECR repo. This comment's own diff is the
# recovery, forcing the slow (full terraform apply) path on the next dispatch.
resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  force_delete = var.use_localstack
}
