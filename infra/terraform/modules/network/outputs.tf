output "network_name" {
  value = google_compute_network.vpc.name
}

output "subnet_self_link" {
  value = google_compute_subnetwork.subnet.self_link
}

output "subnet_cidr" {
  value = google_compute_subnetwork.subnet.ip_cidr_range
}
