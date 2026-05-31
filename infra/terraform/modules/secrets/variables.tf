variable "secrets" {
  type        = map(string)
  sensitive   = true
  description = "Secret ID (== .env var name) -> value. Sourced from secrets.auto.tfvars."
}
