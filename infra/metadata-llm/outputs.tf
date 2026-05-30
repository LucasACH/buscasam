output "internal_ip" {
  value = google_compute_instance.metadata_llm.network_interface[0].network_ip
}

# Set BUSCASAM_METADATA_LLM_URL to this value.
output "metadata_llm_url" {
  value = "http://${google_compute_instance.metadata_llm.network_interface[0].network_ip}:11434"
}
