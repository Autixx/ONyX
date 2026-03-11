#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-onx-api}"
UPSTREAM_HOST="${UPSTREAM_HOST:-127.0.0.1}"
UPSTREAM_PORT="${UPSTREAM_PORT:-8081}"
HTTPS_PORT="${HTTPS_PORT:-443}"
TLS_DOMAIN="${TLS_DOMAIN:-}"
TLS_IP="${TLS_IP:-}"
TLS_CERT_DAYS="${TLS_CERT_DAYS:-825}"
TLS_CERT_DIR="${TLS_CERT_DIR:-/etc/onx/tls}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-onx-api-tls}"
FORCE_REGEN="${FORCE_REGEN:-false}"

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/setup_onx_tls_openssl.sh [options]

Options:
  --service-name <name>   systemd service name (default: onx-api)
  --upstream-host <host>  local upstream host for ONX proxy (default: 127.0.0.1)
  --upstream-port <port>  local upstream port for ONX proxy (default: 8081)
  --https-port <port>     nginx TLS listen port (default: 443)
  --domain <name>         TLS certificate CN/SAN DNS name
  --ip <addr>             TLS certificate SAN IP (recommended: server public IP)
  --cert-days <num>       self-signed cert validity days (default: 825)
  --cert-dir <path>       certificate output directory (default: /etc/onx/tls)
  --nginx-site <name>     nginx site filename prefix (default: onx-api-tls)
  --force                 regenerate certificate even if files exist
  -h, --help              Show help
EOF
}

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --upstream-host)
      UPSTREAM_HOST="$2"
      shift 2
      ;;
    --upstream-port)
      UPSTREAM_PORT="$2"
      shift 2
      ;;
    --https-port)
      HTTPS_PORT="$2"
      shift 2
      ;;
    --domain)
      TLS_DOMAIN="$2"
      shift 2
      ;;
    --ip)
      TLS_IP="$2"
      shift 2
      ;;
    --cert-days)
      TLS_CERT_DAYS="$2"
      shift 2
      ;;
    --cert-dir)
      TLS_CERT_DIR="$2"
      shift 2
      ;;
    --nginx-site)
      NGINX_SITE_NAME="$2"
      shift 2
      ;;
    --force)
      FORCE_REGEN="true"
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ARGS+=("--service-name" "${SERVICE_NAME}")
ARGS+=("--upstream-host" "${UPSTREAM_HOST}")
ARGS+=("--upstream-port" "${UPSTREAM_PORT}")
ARGS+=("--https-port" "${HTTPS_PORT}")
ARGS+=("--cert-days" "${TLS_CERT_DAYS}")
ARGS+=("--cert-dir" "${TLS_CERT_DIR}")
ARGS+=("--nginx-site" "${NGINX_SITE_NAME}")

if [[ -n "${TLS_DOMAIN}" ]]; then
  ARGS+=("--domain" "${TLS_DOMAIN}")
fi
if [[ -n "${TLS_IP}" ]]; then
  ARGS+=("--ip" "${TLS_IP}")
fi
if [[ "${FORCE_REGEN}" == "true" ]]; then
  ARGS+=("--force")
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/setup_tls_openssl.sh" "${ARGS[@]}"
