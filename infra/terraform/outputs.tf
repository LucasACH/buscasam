output "lb_ip" {
  description = "Static LB IP. Set server_name's A record to this, then wait for the cert."
  value       = module.lb.lb_ip
}

output "metadata_llm_url" {
  description = "Set BUSCASAM_METADATA_LLM_URL to this value (null when disabled)."
  value       = one(module.metadata_llm[*].metadata_llm_url)
}

output "image_repo_path" {
  description = "Artifact Registry path prefix for CI to push backend/frontend images."
  value       = module.registry.repo_path
}

output "config_bucket" {
  value = module.registry.config_bucket
}

# GitHub Actions config (set as repo variables).
output "workload_identity_provider" {
  value = module.cicd.workload_identity_provider
}

output "ci_service_account_email" {
  value = module.cicd.ci_service_account_email
}
