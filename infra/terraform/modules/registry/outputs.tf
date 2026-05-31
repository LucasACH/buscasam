output "repo_path" {
  description = "Image path prefix, e.g. us-central1-docker.pkg.dev/PROJECT/buscasam."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.buscasam.repository_id}"
}

output "repo_id" {
  value = google_artifact_registry_repository.buscasam.id
}

output "config_bucket" {
  value = google_storage_bucket.config.name
}

output "config_bucket_id" {
  value = google_storage_bucket.config.id
}
