variable "project_id" {
  type        = string
  description = "GCP project that hosts the metadata-LLM VM."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "network" {
  type    = string
  default = "default"
}

variable "model" {
  type        = string
  default     = "qwen2.5:7b-instruct"
  description = "Ollama model pulled at boot. Must match BUSCASAM_METADATA_LLM_MODEL."
}

variable "running" {
  type        = bool
  default     = true
  description = "RUNNING when true, TERMINATED when false (scale-to-zero)."
}

variable "app_source_ranges" {
  type        = list(string)
  description = "CIDRs allowed to reach Ollama on :11434 (the app/worker subnet)."
}
