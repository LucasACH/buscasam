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

compose pull
compose up -d db
# A failed migrate exits non-zero here, before any app container is rolled.
compose run --rm migrate
compose up -d
docker image prune -f
