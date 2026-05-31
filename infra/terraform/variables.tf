variable "project_id" {
  type        = string
  description = "GCP project that hosts the full BUSCASAM stack."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "server_name" {
  type        = string
  default     = "buscasam.org"
  description = "Public hostname; SERVER_NAME and the Google-managed cert SAN."
}

variable "app_version" {
  type        = string
  description = "Release ref (image tag in AR + config object prefix in GCS) the VM deploys at first boot."
}

variable "embedding_model_revision" {
  type        = string
  default     = ""
  description = "Pinned HF revision SHA (ADR-0002); must be set + pre-staged before TEI starts."
}

variable "github_repo" {
  type        = string
  default     = "LucasACH/buscasam"
  description = "owner/name allowed to push images/config via Workload Identity Federation."
}

variable "secrets" {
  type        = map(string)
  sensitive   = true
  description = "Secret ID (== .env var name) -> value. Set in secrets.auto.tfvars (gitignored)."
}

# --- metadata-llm (infra/terraform/modules/metadata-llm) ---
variable "metadata_llm_model" {
  type    = string
  default = "qwen2.5:7b-instruct"
}

variable "metadata_llm_enabled" {
  type    = bool
  default = false # off at launch (ADR-0012); avoids coupling apply to L4/Spot quota
}

variable "metadata_llm_running" {
  type    = bool
  default = false # scale-to-zero by default; the spot L4 is the biggest cost line
}

variable "metadata_llm_provider" {
  type        = string
  default     = "ollama"
  description = "Metadata LLM provider: vertex (Gemini, prod default) or ollama (ADR-0012)."
}

variable "vertex_project" {
  type        = string
  default     = ""
  description = "GCP project for Vertex AI; empty falls back to project_id."
}

variable "vertex_location" {
  type    = string
  default = "us-central1"
}
