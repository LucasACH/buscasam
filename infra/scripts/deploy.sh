#!/usr/bin/env bash
# ADR-0013 (amends ADR-0009 §12). Pull pre-built images from Artifact Registry,
# migrate, then roll the stack. Images + the infra config tree are produced by CI
# per release ref; the VM already holds the config (startup.sh, or re-pulled from
# the GCS config bucket). Rollback = re-run with the previous ref.
#
#   infra/scripts/deploy.sh <version-ref>
set -euo pipefail

test -n "${1:-}"
export BUSCASAM_VERSION="$1"   # overrides .env; selects the image tag to pull

infra_dir="$(cd "$(dirname "$0")/.." && pwd)"   # repo/infra
cd "$infra_dir"
compose() { docker compose -f compose.yaml -f compose.prod.yaml "$@"; }

# Refresh Artifact Registry auth before pulling. The docker login done at VM boot
# (startup.sh) uses a short-lived (~1h) access token, so a manual deploy run later
# fails with "authentication failed". Re-login with a fresh metadata-server token.
registry_host="$(grep -E '^BUSCASAM_IMAGE_REPO=' .env | head -1 | cut -d= -f2- | cut -d/ -f1)"
if [[ "$registry_host" == *-docker.pkg.dev ]]; then
  token="$(curl -fsS -H 'Metadata-Flavor: Google' \
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' \
    | jq -r .access_token)"
  echo "$token" | docker login -u oauth2accesstoken --password-stdin "https://$registry_host"
fi

compose pull
compose up -d db
# A failed migrate exits non-zero here, before any app container is rolled.
compose run --rm migrate
compose up -d
# Recreated api/frontend get new IPs; nginx caches upstream IPs at start, so
# re-resolve them to avoid stale-upstream 502s after a deploy.
compose restart nginx
docker image prune -f
