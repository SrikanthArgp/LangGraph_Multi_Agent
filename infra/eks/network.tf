locals {
  name_prefix = "${var.project_name}-${var.environment}-eks"

  # "-eks" suffix on the environment segment, not just the name — this stack's SSM parameters
  # (ssm.tf) live at their own path, distinct from infra/lambda-gate's /{project}/{environment}/*
  # and infra/fargate's /{project}/{environment}-ecs/*, so all three stacks' aws_ssm_parameter
  # resources can exist (and be applied/destroyed) independently without a literal SSM
  # parameter-name collision.
  ssm_prefix = "/${var.project_name}/${var.environment}-eks"
}

# Own VPC, not a reference to infra/lambda-gate's or infra/fargate's — same independence
# rationale as infra/fargate/network.tf's identical comment: this stack doesn't depend on either
# other stack at any layer, so it can be applied or destroyed on its own. Public subnets + an
# Internet Gateway (not private subnets + NAT Gateway), same as Phase 16 — node-group worker
# nodes only need outbound access to Supabase/Upstash/OpenAI/Tavily/ECR (plan.md step 2), which a
# public IP + IGW route satisfies without a ~$32/month NAT Gateway.
data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = "10.1.0.0/16" # distinct /16 from infra/fargate's 10.0.0.0/16 — no peering between the two, just avoiding an accidental CIDR collision if that ever changes
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${local.name_prefix}-igw" }
}

# Two AZs — same minimum infra/fargate/network.tf uses for its ALB; EKS itself also requires
# subnets in at least two AZs for cluster creation to succeed at all.
#
# The two kubernetes.io/* tags are the one networking wrinkle Phase 16's plain ECS/ALB Terraform
# never needed (plan.md step 2): the EKS control plane and the AWS Load Balancer Controller (a
# Helm-installed cluster addon, not a Terraform resource — see gitops/multi-agent's future
# dependency) both discover which subnets they're allowed to use for cluster networking and
# provisioned load balancers by tag, not by an explicit subnet_ids argument passed to either.
# Easy to miss since neither Lambda's nor plain ECS's Terraform reads these tags at all.
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = "10.1.${count.index + 1}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                         = "${local.name_prefix}-public-${count.index}"
    "kubernetes.io/cluster/${local.name_prefix}" = "shared"
    "kubernetes.io/role/elb"                     = "1"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = { Name = "${local.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
