output "secret_ids" {
  description = "Secret IDs (== .env var names) for the VM startup to fetch."
  value       = [for s in google_secret_manager_secret.this : s.secret_id]
}
