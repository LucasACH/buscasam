variable "server_name" {
  type = string
}

variable "instance_group" {
  type        = string
  description = "Backend instance group self_link (the app VM)."
}
