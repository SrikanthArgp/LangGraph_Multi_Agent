# Same-account Lambda pulls need no repository policy (see enterprize-deploy-steps.md's
# wiring table) — only cross-account pulls would.
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"

  force_delete = var.use_localstack
}
