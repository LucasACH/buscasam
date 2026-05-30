terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Spot L4 keeps the GPU ~70% cheaper. Indexing is an async background job and
# an Ollama outage is non-fatal (suggest_metadata falls back to heuristics), so
# preemption only delays the queue — it never fails a document.
resource "google_compute_instance" "metadata_llm" {
  name         = "buscasam-metadata-llm"
  machine_type = "g2-standard-4"
  zone         = var.zone
  tags         = ["buscasam-metadata-llm"]

  scheduling {
    provisioning_model          = "SPOT"
    preemptible                 = true
    automatic_restart           = false
    on_host_maintenance         = "TERMINATE"
    instance_termination_action = "STOP"
  }

  guest_accelerator {
    type  = "nvidia-l4"
    count = 1
  }

  boot_disk {
    initialize_params {
      image = "projects/ml-images/global/images/family/common-cu123"
      size  = 50
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = var.network
    # No external IP: only the app/worker subnet reaches Ollama, over the
    # internal network (see the firewall rule below).
  }

  metadata = {
    install-nvidia-driver = "True"
    startup-script = templatefile("${path.module}/startup.sh", {
      model = var.model
    })
  }

  # Scale-to-zero: set `running = false` to STOP the instance when the index
  # queue is idle. Safe because metadata generation degrades to heuristics.
  desired_status = var.running ? "RUNNING" : "TERMINATED"

  allow_stopping_for_update = true
}

resource "google_compute_firewall" "metadata_llm_ollama" {
  name    = "buscasam-metadata-llm-ollama"
  network = var.network

  allow {
    protocol = "tcp"
    ports    = ["11434"]
  }

  source_ranges = var.app_source_ranges
  target_tags   = ["buscasam-metadata-llm"]
}
