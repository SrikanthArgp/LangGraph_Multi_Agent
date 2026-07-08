variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "localstack"
}

# Flips every LocalStack-only provider setting below. Set to false (via
# -var="use_localstack=false") once pointing this same config at real AWS in Stage C.
variable "use_localstack" {
  type    = bool
  default = true
}

variable "state_bucket_name" {
  type    = string
  default = "crag-terraform-state"
}

variable "state_lock_table_name" {
  type    = string
  default = "crag-terraform-locks"
}
