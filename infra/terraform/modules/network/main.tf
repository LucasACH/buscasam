# Dedicated VPC. The app VM carries an external IP for egress (image pulls,
# model pre-stage); no Cloud NAT. A GPU VM (ollama, count=0) would need its own
# egress path if ever re-enabled.
resource "google_compute_network" "vpc" {
  name                    = "buscasam"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "buscasam"
  network       = google_compute_network.vpc.id
  region        = var.region
  ip_cidr_range = var.subnet_cidr
}

# SSH via Identity-Aware Proxy, so `gcloud compute ssh` works without a public IP.
resource "google_compute_firewall" "iap_ssh" {
  name          = "buscasam-iap-ssh"
  network       = google_compute_network.vpc.id
  source_ranges = ["35.235.240.0/20"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# GCP HTTPS LB front-ends + health checks reach the app VM on :80.
resource "google_compute_firewall" "lb_to_app" {
  name          = "buscasam-lb-to-app"
  network       = google_compute_network.vpc.id
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["buscasam-app"]
  allow {
    protocol = "tcp"
    ports    = ["80"]
  }
}
