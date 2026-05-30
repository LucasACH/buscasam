#!/usr/bin/env bash
# ADR-0009 §10. Pre-stage the pinned TEI model into the VM's tei-cache so the
# container can start with HF_HUB_OFFLINE=1. Run from a workstation that can
# reach huggingface.co and scp to the GCE VM. Requires `huggingface-cli`.
#
#   EMBEDDING_MODEL_REVISION=<sha> VM_HOST=user@vm infra/scripts/prestage_model.sh
set -euo pipefail

MODEL_ID="${EMBEDDING_MODEL_ID:-intfloat/multilingual-e5-large}"
REVISION="${EMBEDDING_MODEL_REVISION:?set EMBEDDING_MODEL_REVISION to the pinned HF SHA}"
VM_HOST="${VM_HOST:?set VM_HOST, e.g. buscasam@buscasam-vm}"
REMOTE_CACHE="${REMOTE_CACHE:-/var/lib/buscasam/tei-cache}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# Download the exact revision into an HF-hub cache layout (models--owner--name/…),
# which is what TEI reads from /data when offline.
huggingface-cli download "$MODEL_ID" \
    --revision "$REVISION" \
    --cache-dir "$workdir/tei-cache"

tar -C "$workdir" -czf "$workdir/tei-cache.tgz" tei-cache

# Stage on the VM (sudo: the cache dir is owned by buscasam:buscasam, mode-guarded).
scp "$workdir/tei-cache.tgz" "$VM_HOST:/tmp/tei-cache.tgz"
ssh "$VM_HOST" "sudo mkdir -p '$REMOTE_CACHE' \
    && sudo tar -C '$REMOTE_CACHE' --strip-components=1 -xzf /tmp/tei-cache.tgz \
    && sudo chown -R buscasam:buscasam '$REMOTE_CACHE' \
    && rm -f /tmp/tei-cache.tgz"

echo "Staged $MODEL_ID@$REVISION to $VM_HOST:$REMOTE_CACHE"
echo "Set EMBEDDING_MODEL_REVISION=$REVISION in infra/.env before deploy."
