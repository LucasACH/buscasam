variable "github_repo" {
  type        = string
  description = "owner/name, e.g. LucasACH/buscasam. Restricts which repo can mint tokens."
}

variable "ar_repo_id" {
  type        = string
  description = "Artifact Registry repository id (full resource id) to grant writer on."
}

variable "config_bucket_id" {
  type        = string
  description = "GCS config bucket id to grant object admin on."
}
