#!/usr/bin/env bash
# ADR-0009 §10. Pre-stage the pinned TEI model into the VM's tei-cache so the
# container can start with HF_HUB_OFFLINE=1. Run from a workstation that can
# reach huggingface.co and the GCE VM through IAP. Requires `gcloud` and
# `huggingface-cli`.
#
#   EMBEDDING_MODEL_REVISION=<sha> VM_ZONE=<zone> infra/scripts/prestage_model.sh
set -euo pipefail

MODEL_ID="${EMBEDDING_MODEL_ID:-intfloat/multilingual-e5-large}"
REVISION="${EMBEDDING_MODEL_REVISION:?set EMBEDDING_MODEL_REVISION to the pinned HF SHA}"
VM_HOST="${VM_HOST:-buscasam-app}"
VM_ZONE="${VM_ZONE:?set VM_ZONE, e.g. us-central1-a}"
REMOTE_CACHE="${REMOTE_CACHE:-/var/lib/buscasam/tei-cache}"
gcloud_args=(--tunnel-through-iap --zone "$VM_ZONE")
if [[ -n "${GCP_PROJECT:-}" ]]; then
    gcloud_args+=(--project "$GCP_PROJECT")
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# Download the exact revision into an HF-hub cache layout (models--owner--name/…),
# which is what TEI reads from /data when offline.
huggingface-cli download "$MODEL_ID" \
    --revision "$REVISION" \
    --cache-dir "$workdir/tei-cache"

tar -C "$workdir" -czf "$workdir/tei-cache.tgz" tei-cache

# Stage on the VM (sudo: the cache dir is owned by buscasam:buscasam, mode-guarded).
gcloud compute scp "${gcloud_args[@]}" "$workdir/tei-cache.tgz" "$VM_HOST:/tmp/tei-cache.tgz"
gcloud compute ssh "${gcloud_args[@]}" "$VM_HOST" --command "sudo mkdir -p '$REMOTE_CACHE' \
    && sudo tar -C '$REMOTE_CACHE' --strip-components=1 -xzf /tmp/tei-cache.tgz \
    && sudo chown -R buscasam:buscasam '$REMOTE_CACHE' \
    && rm -f /tmp/tei-cache.tgz"

echo "Staged $MODEL_ID@$REVISION to $VM_HOST:$REMOTE_CACHE"
echo "Set EMBEDDING_MODEL_REVISION=$REVISION in infra/.env before deploy."
