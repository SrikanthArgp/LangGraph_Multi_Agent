# Same-account Lambda pulls need no repository policy (see enterprize-deploy-steps.md's
# wiring table) — only cross-account pulls would.
#
# LocalStack instances are ephemeral — a restarted/reset one has none of this stack's resources,
# even though this repo's git state (and Terraform's remote state, once infra/bootstrap/ is
# reapplied) says otherwise. cd-lambda.yml's own path-filter only runs its full
# init/apply/build-and-push path when a commit's diff touches infra/lambda-gate/**, so a
# non-infra commit against a freshly reset LocalStack hits the exact chicken-and-egg gap
# completed.md's Phase 18/19 entry already documents (empty ECR breaks `aws ecr
# get-login-password`). Recovering from that should always go through a real CD run whose diff
# touches this directory (so the workflow's own steps do the work) — never by manually running
# infra/lambda-gate/scripts/*.sh or hand-invoking docker/terraform outside the workflow, since
# that only hides the gap instead of proving the pipeline can self-heal.
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"

  force_delete = var.use_localstack
}
