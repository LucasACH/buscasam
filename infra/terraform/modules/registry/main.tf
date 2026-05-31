# Docker images (backend, frontend) built+pushed by CI, pulled on the app VM.
resource "google_artifact_registry_repository" "buscasam" {
  location      = var.region
  repository_id = "buscasam"
  format        = "DOCKER"
}

# Versioned infra config (compose*, nginx/, postgresql.conf, scripts/) tarballs,
# one per release ref. The app VM pulls its ref at boot instead of cloning the
# private repo.
resource "google_storage_bucket" "config" {
  name                        = "${var.project_id}-buscasam-config"
  location                    = var.region
  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }
}
