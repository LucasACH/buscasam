# One Secret Manager secret per .env secret. The app VM's service account reads
# these at boot to assemble /opt/buscasam/infra/.env. Secret ID == .env var name.
# Keys (secret IDs) are not sensitive; only the values are. nonsensitive() lets
# them drive for_each.
resource "google_secret_manager_secret" "this" {
  for_each  = nonsensitive(toset(keys(var.secrets)))
  secret_id = each.key
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "this" {
  for_each    = google_secret_manager_secret.this
  secret      = each.value.id
  secret_data = var.secrets[each.key]
}
