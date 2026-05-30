#!/usr/bin/env bash
# ADR-0009 §11. Daily backup loop for the `backup` container: run one recovery
# point, then sleep until the next day. A failed run is logged and retried on
# the next tick; the completion marker keeps partial runs from being trusted.
set -euo pipefail

interval="${BACKUP_INTERVAL_SECONDS:-86400}"

while true; do
  if python /app/scripts/backup_run.py; then
    :
  else
    echo "backup run failed (exit $?); retrying next tick" >&2
  fi
  sleep "$interval"
done
