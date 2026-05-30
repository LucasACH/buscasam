#!/usr/bin/env bash
# ADR-0009 §12 (as amended for the infra/ layout). Build on the host from an
# explicit git commit/tag, migrate, then roll the stack. Rollback = re-run with
# the previous commit/tag.
#
#   infra/scripts/deploy.sh <commit-or-tag>
set -euo pipefail

test -n "${1:-}"
ref="$1"

infra_dir="$(cd "$(dirname "$0")/.." && pwd)"   # repo/infra
repo_dir="$(cd "$infra_dir/.." && pwd)"

git -C "$repo_dir" fetch --tags origin
git -C "$repo_dir" checkout --detach "$ref"

cd "$infra_dir"
compose() { docker compose -f compose.yaml -f compose.prod.yaml "$@"; }

compose build
compose up -d db
# A failed migrate exits non-zero here, before any app container is rolled.
compose run --rm migrate
compose up -d
docker image prune -f
