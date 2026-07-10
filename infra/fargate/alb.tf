resource "aws_lb" "this" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

# target_type "ip", not "instance" — required for awsvpc network mode (ecs.tf), since each task
# gets its own ENI/IP rather than sharing the host instance's.
resource "aws_lb_target_group" "backend" {
  name        = "${local.name_prefix}-backend"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.this.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }
}

# HTTP only, not HTTPS — an ALB listener needs its own ACM certificate to terminate TLS, and this
# phase has no custom domain to validate one against (same constraint
# infra/lambda-gate/cloudfront.tf's viewer_certificate already accepted — see network.tf's
# aws_security_group.alb comment). CloudFront still terminates HTTPS for every viewer at its own
# edge with the default *.cloudfront.net cert (cloudfront.tf); only this ALB-to-CloudFront hop is
# plain HTTP.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
