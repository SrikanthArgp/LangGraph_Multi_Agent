resource "aws_ecs_cluster" "this" {
  name = local.name_prefix

  # No charge for the cluster itself, only running tasks are billed (plan.md Phase 16 step 2).
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}-backend"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      essential = true

      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]

      # Same two env vars infra/lambda-gate/lambda.tf's local.common_env sets trigger the same
      # backend/config.py bootstrap_env() code path Lambda uses — but pointed at this stack's own
      # SSM prefix (local.ssm_prefix, ssm.tf), not infra/lambda-gate/'s, since this stack's
      # secrets are its own aws_ssm_parameter resources, not a read of lambda-gate's.
      # CHROMA_PERSIST_DIR is deliberately NOT set here (unlike Lambda): Fargate's task root
      # filesystem is writable everywhere, not read-only outside /tmp the way Lambda's is, so
      # multi_agent/ingestion.py's baked-in _CHROMA_SEED_DIR can be opened in place directly,
      # exactly as it already does in Docker Compose.
      environment = [
        { name = "APP_ENV", value = "production" },
        { name = "SSM_PARAMETER_PREFIX", value = local.ssm_prefix },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = var.container_port
  }

  # Give the container time to pass its first health check before the ALB starts counting
  # failures against it.
  health_check_grace_period_seconds = 30

  # Matters more here than it would elsewhere in this plan: this service runs at desired_count 1
  # (plan.md's explicit cost/availability tradeoff), so a bad deploy has no healthy replica to
  # hide behind. A task that keeps failing its ALB health check gets auto-reverted to the last
  # known-good task definition revision without waiting for cd-ecs.yml's own smoke check to
  # notice — see cd-ecs-deploy-steps.md's "Why a new task definition revision every time" section.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Comment-only touch (2026-07-12): dorny/paths-filter diffs only the latest commit on a
  # workflow_call trigger (no push before/after context), so this file needs re-touching
  # alongside each cd-ecs.yml fix commit during this same verification pass, until the first
  # full apply actually lands — see infra/lambda-gate/lambda.tf's matching comment.

  depends_on = [aws_lb_listener.http]
}

# Target-tracking on CPU (plan.md Phase 16 step 4) — a native AWS resource, no
# cluster-autoscaler/metrics-server equivalent to install, unlike the EKS alternative (Phase 20).
resource "aws_appautoscaling_target" "backend" {
  max_capacity       = var.max_task_count
  min_capacity       = var.min_task_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${local.name_prefix}-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.cpu_target_value
  }
}
