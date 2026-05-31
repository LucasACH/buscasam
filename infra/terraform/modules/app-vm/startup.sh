#!/usr/bin/env bash
# First-boot bootstrap for the BUSCASAM app VM (auto-deploy, ADR-0013).
# Mount data disk -> install Docker -> assemble .env from Secret Manager ->
# pull config tarball from GCS -> deploy.sh (pulls images from Artifact Registry).
set -euo pipefail
exec > >(tee -a /var/log/buscasam-startup.log) 2>&1
echo "=== buscasam startup $(date -u) ==="

PROJECT="${project_id}"
REGION="${region}"
IMAGE_REPO="${image_repo}"
CONFIG_BUCKET="${config_bucket}"
VERSION="${app_version}"
SECRET_IDS="${secret_ids}"

# --- data disk: format on first boot, mount at /var/lib/buscasam ---
DEV=/dev/disk/by-id/google-buscasam-data
if ! blkid "$DEV"; then
  mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0,discard "$DEV"
fi
mkdir -p /var/lib/buscasam
grep -q "$DEV" /etc/fstab || echo "$DEV /var/lib/buscasam ext4 discard,defaults,nofail 0 2" >> /etc/fstab
mount -a

# --- packages: Docker (+ compose plugin), jq ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y jq ca-certificates curl
curl -fsSL https://get.docker.com | sh

# --- host user + state dirs (ADR-0009 §7) ---
id buscasam >/dev/null 2>&1 || useradd --system --uid 1000 --user-group --shell /usr/sbin/nologin buscasam
usermod -aG docker buscasam || true
mkdir -p /var/lib/buscasam/postgres /var/lib/buscasam/blobs/.tmp /var/lib/buscasam/tei-cache /var/lib/buscasam/backup
chown -R buscasam:buscasam /var/lib/buscasam

TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" | jq -r .access_token)

# --- docker auth to Artifact Registry via the VM service account ---
echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGION-docker.pkg.dev"

# --- pull versioned infra config (compose*, nginx/, postgresql.conf, scripts/) ---
mkdir -p /opt/buscasam
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "https://storage.googleapis.com/storage/v1/b/$CONFIG_BUCKET/o/$VERSION%2Fconfig.tgz?alt=media" \
  -o /tmp/config.tgz
tar -xzf /tmp/config.tgz -C /opt/buscasam

# --- assemble /opt/buscasam/infra/.env ---
declare -A S
for id in $SECRET_IDS; do
  S[$id]=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT/secrets/$id/versions/latest:access" \
    | jq -r .payload.data | base64 -d)
done

ENV=/opt/buscasam/infra/.env
umask 077
cat > "$ENV" <<EOF
BUSCASAM_VERSION=$VERSION
BUSCASAM_IMAGE_REPO=$IMAGE_REPO
EMBEDDING_MODEL_ID=intfloat/multilingual-e5-large
EMBEDDING_MODEL_REVISION=${embedding_model_revision}

POSTGRES_USER=buscasam
POSTGRES_PASSWORD=$${S[POSTGRES_PASSWORD]}
POSTGRES_DB=buscasam

BUSCASAM_ENV=prod
BUSCASAM_DATABASE_URL=postgresql+psycopg://buscasam:$${S[POSTGRES_PASSWORD]}@db:5432/buscasam
BUSCASAM_TEI_URL=http://tei
BUSCASAM_BASE_URL=https://${server_name}
BUSCASAM_INTERNAL_API_URL=http://api:8000/api
BUSCASAM_BLOB_ROOT=/var/lib/buscasam/blobs
BUSCASAM_MIN_SEMANTIC_SIMILARITY=0.78
BUSCASAM_EMBED_QUERY_TIMEOUT_S=0.5
BUSCASAM_EXTRACT_PIPELINE_VERSION=extract-v2
BUSCASAM_SECRET_KEY=$${S[BUSCASAM_SECRET_KEY]}
BUSCASAM_OIDC_CLIENT_ID=$${S[BUSCASAM_OIDC_CLIENT_ID]}
BUSCASAM_OIDC_CLIENT_SECRET=$${S[BUSCASAM_OIDC_CLIENT_SECRET]}

BUSCASAM_METADATA_LLM_ENABLED=0
BUSCASAM_METADATA_LLM_URL=http://localhost:11434
BUSCASAM_METADATA_LLM_MODEL=qwen2.5:7b-instruct

BACKUP_RETENTION_DAYS=14

TLS_MODE=upstream
SERVER_NAME=${server_name}
TRUSTED_PROXY_CIDR=${trusted_proxy_cidr}
EOF
chown buscasam:buscasam "$ENV"

# --- deploy (pull images, migrate, up) ---
bash /opt/buscasam/infra/scripts/deploy.sh "$VERSION"
echo "=== buscasam startup done $(date -u) ==="
