# Dedicated VPC. The app and GPU VMs run with no external IP; egress (image
# pulls, model pre-stage) goes through Cloud NAT.
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

resource "google_compute_router" "router" {
  name    = "buscasam"
  network = google_compute_network.vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  name                               = "buscasam"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
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
