# Values the GitHub Actions workflow needs (set as repo variables/secrets).
output "workload_identity_provider" {
  description = "Full provider resource name for google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "ci_service_account_email" {
  value = google_service_account.ci.email
}

output "deploy_service_account_email" {
  value = google_service_account.deploy.email
}

output "deploy_service_account_member" {
  value = "serviceAccount:${google_service_account.deploy.email}"
}
