#!/bin/bash
set -euo pipefail

curl -fsSL https://ollama.com/install.sh | sh

# Bind to all interfaces so the app/worker subnet can reach Ollama; the
# firewall (not localhost) is what restricts access.
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

systemctl daemon-reload
systemctl restart ollama

ollama pull ${model}
