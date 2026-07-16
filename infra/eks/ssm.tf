# Own copy of infra/lambda-gate/ssm.tf's and infra/fargate/ssm.tf's secrets, at this stack's own
# path (local.ssm_prefix, network.tf) — not a read of either other stack's parameters. Same
# deliberate-duplication rationale as infra/fargate/ssm.tf's identical comment: this stack's pod
# (via backend_irsa, iam.tf) can fetch its own secrets even if the other two stacks were never
# applied or have since been destroyed. Cost is the same too: secret values
# (infra/eks/secrets.auto.tfvars, gitignored) need to be kept in sync with the other two stacks'
# secrets.auto.tfvars by hand.
#
# for_each can't iterate var.secrets directly — Terraform refuses a sensitive value as a for_each
# argument. The key *names* aren't secret, only the values are, so it's safe to iterate the
# nonsensitive key set and look each value up from the still-sensitive map.
resource "aws_ssm_parameter" "secrets" {
  for_each = nonsensitive(toset(keys(var.secrets)))

  name  = "${local.ssm_prefix}/${each.value}"
  type  = "SecureString"
  value = var.secrets[each.value]
}
