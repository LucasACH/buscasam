variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "network" {
  type = string
}

variable "subnetwork" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "data_disk_gb" {
  type    = number
  default = 50
}

variable "image_repo" {
  type        = string
  description = "Artifact Registry path prefix (region-docker.pkg.dev/project/buscasam)."
}

variable "config_bucket" {
  type = string
}

variable "ar_repo_id" {
  type = string
}

variable "config_bucket_id" {
  type = string
}

variable "app_version" {
  type        = string
  description = "Release ref: image tag in AR and config object prefix in GCS, pulled at first boot."
}

variable "server_name" {
  type = string
}

variable "trusted_proxy_cidr" {
  type    = string
  default = "130.211.0.0/22,35.191.0.0/16"
}

variable "embedding_model_revision" {
  type        = string
  default     = ""
  description = "Pinned HF revision SHA (ADR-0002). Must be set + pre-staged before TEI can start."
}

variable "secret_ids" {
  type        = list(string)
  description = "Secret Manager IDs (== .env var names) the VM fetches at boot."
}

variable "metadata_llm_enabled" {
  type    = bool
  default = false
}

variable "metadata_llm_provider" {
  type        = string
  default     = "ollama"
  description = "Metadata LLM provider written to .env: ollama or vertex (ADR-0012)."
}

variable "metadata_llm_model" {
  type    = string
  default = "qwen2.5:7b-instruct"
}

variable "vertex_project" {
  type        = string
  default     = ""
  description = "GCP project for Vertex AI (provider=vertex). Defaults to project_id when empty."
}

variable "vertex_location" {
  type    = string
  default = "us-central1"
}
