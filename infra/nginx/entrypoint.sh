#!/bin/sh
# ADR-0009 §9: render the active TLS-mode server block, then run nginx.
set -eu

: "${TLS_MODE:=upstream}"
: "${SERVER_NAME:=_}"
: "${TRUSTED_PROXY_CIDR:=0.0.0.0/0}"

template="/etc/nginx/templates/${TLS_MODE}.conf.template"
if [ ! -f "$template" ]; then
    echo "entrypoint: unknown TLS_MODE='${TLS_MODE}' (expected upstream|self)" >&2
    exit 1
fi

# Expand the comma/space-separated CIDR list into one directive per entry;
# nginx has no loop and accepts only a single CIDR per set_real_ip_from.
REAL_IP_FROM=""
oldifs=$IFS
IFS=', '
for cidr in $TRUSTED_PROXY_CIDR; do
    [ -n "$cidr" ] && REAL_IP_FROM="${REAL_IP_FROM}set_real_ip_from ${cidr};
    "
done
IFS=$oldifs
export REAL_IP_FROM

mkdir -p /etc/nginx/conf.d
envsubst '${SERVER_NAME} ${REAL_IP_FROM}' < "$template" > /etc/nginx/conf.d/default.conf

nginx -t
exec nginx -g 'daemon off;'
