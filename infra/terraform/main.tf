# Root module. Wires the GCP footprint together; one `terraform apply` from here
# brings up the whole BUSCASAM stack. Provider config lives in versions.tf.
#
# Modules land incrementally (see scratchpad.md build phases):
#   network · secrets · registry · cicd · app-vm · lb · metadata-llm

module "network" {
  source = "./modules/network"
  region = var.region

  depends_on = [google_project_service.apis]
}

module "registry" {
  source     = "./modules/registry"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "secrets" {
  source  = "./modules/secrets"
  secrets = var.secrets

  depends_on = [google_project_service.apis]
}

module "cicd" {
  source           = "./modules/cicd"
  github_repo      = var.github_repo
  ar_repo_id       = module.registry.repo_id
  config_bucket_id = module.registry.config_bucket_id

  depends_on = [google_project_service.apis]
}

module "app_vm" {
  source     = "./modules/app-vm"
  project_id = var.project_id
  region     = var.region
  zone       = var.zone
  network    = module.network.network_name
  subnetwork = module.network.subnet_self_link

  image_repo               = module.registry.repo_path
  config_bucket            = module.registry.config_bucket
  config_bucket_id         = module.registry.config_bucket_id
  ar_repo_id               = module.registry.repo_id
  app_version              = var.app_version
  server_name              = var.server_name
  embedding_model_revision = var.embedding_model_revision
  metadata_llm_enabled     = var.metadata_llm_enabled
  metadata_llm_provider    = var.metadata_llm_provider
  metadata_llm_model       = var.metadata_llm_model
  vertex_project           = var.vertex_project
  vertex_location          = var.vertex_location
  secret_ids               = module.secrets.secret_ids
  deploy_sa_member         = module.cicd.deploy_service_account_member
}

module "lb" {
  source         = "./modules/lb"
  server_name    = var.server_name
  instance_group = module.app_vm.instance_group
}

module "metadata_llm" {
  source = "./modules/metadata-llm"
  # Self-hosted GPU VM only for the ollama provider; vertex uses Vertex AI.
  count = var.metadata_llm_enabled && var.metadata_llm_provider == "ollama" ? 1 : 0

  zone       = var.zone
  network    = module.network.network_name
  subnetwork = module.network.subnet_self_link
  model      = var.metadata_llm_model
  running    = var.metadata_llm_running
  # Only the app/worker subnet may reach Ollama on :11434.
  app_source_ranges = [module.network.subnet_cidr]
}
