output "lb_ip" {
  description = "Reserved static IP. Point server_name's A record here."
  value       = google_compute_global_address.lb.address
}
