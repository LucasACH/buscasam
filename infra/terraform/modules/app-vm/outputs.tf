output "instance_group" {
  description = "Unmanaged instance group, the LB backend."
  value       = google_compute_instance_group.app.self_link
}

output "instance_name" {
  value = google_compute_instance.app.name
}

output "internal_ip" {
  value = google_compute_instance.app.network_interface[0].network_ip
}
