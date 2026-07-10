# Own copy of infra/lambda-gate/ssm.tf's secrets, at this stack's own path (local.ssm_prefix,
# network.tf) — not a read of infra/lambda-gate/'s parameters. Deliberate duplication, not an
# oversight: this stack doesn't depend on infra/lambda-gate/ at any layer, including runtime
# secret reads, so its ECS tasks can fetch secrets even if infra/lambda-gate/ was never applied
# (or was destroyed). Cost is real: secret values (infra/fargate/secrets.auto.tfvars, gitignored)
# now need to be kept in sync with infra/lambda-gate/secrets.auto.tfvars by hand.
#
# for_each can't iterate var.secrets directly — Terraform refuses a sensitive value as a
# for_each argument. The key *names* aren't secret, only the values are, so it's safe to iterate
# the nonsensitive key set and look each value up from the still-sensitive map.
resource "aws_ssm_parameter" "secrets" {
  for_each = nonsensitive(toset(keys(var.secrets)))

  name  = "${local.ssm_prefix}/${each.value}"
  type  = "SecureString"
  value = var.secrets[each.value]
}
