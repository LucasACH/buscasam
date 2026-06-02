data "google_project" "this" {}

# Keyless GitHub Actions -> GCP trust (Workload Identity Federation). No JSON key.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # Only this repo may exchange a token. Required by GCP when mapping repository.
  attribute_condition = "assertion.repository == \"${var.github_repo}\""
}

# Identity the workflow impersonates to push images + config.
resource "google_service_account" "ci" {
  account_id   = "buscasam-ci"
  display_name = "BUSCASAM CI (GitHub Actions)"
}

# Let workflows from this repo impersonate the CI SA.
resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  repository = var.ar_repo_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_storage_bucket_iam_member" "ci_config_writer" {
  bucket = var.config_bucket_id
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ci.email}"
}

# Identity the `deploy` job impersonates to roll the app VM via IAP SSH (ADR-0013).
# Separate from the CI SA so prod-access blast radius stays off the build identity;
# its only powers are instance-scoped (osAdminLogin + IAP tunnel), granted in
# app-vm against the single VM.
resource "google_service_account" "deploy" {
  account_id   = "buscasam-deploy"
  display_name = "BUSCASAM deploy (GitHub Actions)"
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# Read-only lookups `gcloud compute ssh` makes before tunnelling (project SSH/OS
# Login config + instance details). Scoped to exactly those gets, not compute.viewer.
resource "google_project_iam_custom_role" "deploy_ssh" {
  role_id     = "buscasamDeploySsh"
  title       = "BUSCASAM deploy SSH"
  description = "Minimal read perms gcloud compute ssh needs to resolve the app VM."
  permissions = [
    "compute.projects.get",
    "compute.instances.get",
    "compute.instances.list",
  ]
}

resource "google_project_iam_member" "deploy_ssh" {
  project = data.google_project.this.project_id
  role    = google_project_iam_custom_role.deploy_ssh.id
  member  = "serviceAccount:${google_service_account.deploy.email}"
}
