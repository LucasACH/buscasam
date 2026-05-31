# Stateful app host: the whole Docker Compose stack (ADR-0009) on one VM.
# No external IP — LB fronts :80, egress via Cloud NAT, SSH via IAP.
resource "google_service_account" "app" {
  account_id   = "buscasam-app"
  display_name = "BUSCASAM app VM"
}

# Read secrets into .env, pull images from AR, pull config from GCS, ship logs.
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_artifact_registry_repository_iam_member" "app_reader" {
  repository = var.ar_repo_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.app.email}"
}

resource "google_storage_bucket_iam_member" "app_config_reader" {
  bucket = var.config_bucket_id
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.app.email}"
}

# Vertex AI metadata LLM (ADR-0012) authenticates via ADC = this SA.
resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# Persistent state (PGDATA, blobs, tei-cache). Survives VM recreation.
resource "google_compute_disk" "data" {
  name = "buscasam-data"
  type = "pd-balanced"
  zone = var.zone
  size = var.data_disk_gb
}

resource "google_compute_instance" "app" {
  name         = "buscasam-app"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["buscasam-app"]

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "buscasam-data"
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork
    # No access_config block => no external IP.
  }

  service_account {
    email  = google_service_account.app.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup.sh", {
      project_id               = var.project_id
      region                   = var.region
      image_repo               = var.image_repo
      config_bucket            = var.config_bucket
      app_version              = var.app_version
      server_name              = var.server_name
      trusted_proxy_cidr       = var.trusted_proxy_cidr
      embedding_model_revision = var.embedding_model_revision
      metadata_llm_enabled     = var.metadata_llm_enabled
      metadata_llm_provider    = var.metadata_llm_provider
      metadata_llm_model       = var.metadata_llm_model
      vertex_project           = coalesce(var.vertex_project, var.project_id)
      vertex_location          = var.vertex_location
      secret_ids               = join(" ", var.secret_ids)
    })
  }

  allow_stopping_for_update = true
}

# Unmanaged instance group: the LB backend wrapping the single stateful VM.
resource "google_compute_instance_group" "app" {
  name      = "buscasam-app"
  zone      = var.zone
  instances = [google_compute_instance.app.self_link]
  named_port {
    name = "http"
    port = 80
  }
}
