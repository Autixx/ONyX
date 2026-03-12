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
  --upstream-host <host>  local upstream host for ONyX proxy (default: 127.0.0.1)
  --upstream-port <port>  local upstream port for ONyX proxy (default: 8081)
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

fail() {
  echo "$*" >&2
  exit 1
}

validate_port() {
  local value="$1"
  [[ "${value}" =~ ^[0-9]{1,5}$ ]] || return 1
  (( value >= 1 && value <= 65535 ))
}

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
      fail "Unknown argument: $1"
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root: sudo bash $0"
fi

validate_port "${UPSTREAM_PORT}" || fail "Invalid upstream port: ${UPSTREAM_PORT}"
validate_port "${HTTPS_PORT}" || fail "Invalid https port: ${HTTPS_PORT}"
[[ "${TLS_CERT_DAYS}" =~ ^[0-9]+$ ]] || fail "cert-days must be a positive integer."
(( TLS_CERT_DAYS >= 1 )) || fail "cert-days must be >= 1."

if [[ -z "${TLS_DOMAIN}" && -z "${TLS_IP}" ]]; then
  TLS_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

[[ -n "${TLS_DOMAIN}" || -n "${TLS_IP}" ]] || fail "Provide --domain or --ip for certificate SAN."

echo "[tls] Installing nginx and openssl..."
apt-get update
apt-get install -y nginx openssl

mkdir -p "${TLS_CERT_DIR}"
chmod 700 "${TLS_CERT_DIR}"

CERT_KEY="${TLS_CERT_DIR}/panel.key"
CERT_CRT="${TLS_CERT_DIR}/panel.crt"
CERT_CFG="${TLS_CERT_DIR}/openssl-panel.cnf"
NGINX_SITE_PATH="/etc/nginx/sites-available/${NGINX_SITE_NAME}.conf"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/${NGINX_SITE_NAME}.conf"

if [[ ! -f "${CERT_KEY}" || ! -f "${CERT_CRT}" || "${FORCE_REGEN}" == "true" ]]; then
  DNS_LINE=""
  IP_LINE=""
  if [[ -n "${TLS_DOMAIN}" ]]; then
    DNS_LINE="DNS.1 = ${TLS_DOMAIN}"
  fi
  if [[ -n "${TLS_IP}" ]]; then
    IP_LINE="IP.1 = ${TLS_IP}"
  fi

  cat > "${CERT_CFG}" <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]
CN = ${TLS_DOMAIN:-${TLS_IP}}
O = ONyX
OU = Control Plane

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.100 = localhost
IP.100 = 127.0.0.1
${DNS_LINE}
${IP_LINE}
EOF

  echo "[tls] Generating self-signed certificate..."
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout "${CERT_KEY}" \
    -out "${CERT_CRT}" \
    -days "${TLS_CERT_DAYS}" \
    -config "${CERT_CFG}" \
    -extensions v3_req
  chmod 600 "${CERT_KEY}"
  chmod 644 "${CERT_CRT}"
else
  echo "[tls] Existing certificate found, reusing."
fi

echo "[tls] Writing nginx TLS reverse-proxy config..."
cat > "${NGINX_SITE_PATH}" <<EOF
server {
    listen ${HTTPS_PORT} ssl http2;
    listen [::]:${HTTPS_PORT} ssl http2;
    server_name ${TLS_DOMAIN:-_};

    ssl_certificate ${CERT_CRT};
    ssl_certificate_key ${CERT_KEY};
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://${UPSTREAM_HOST}:${UPSTREAM_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name ${TLS_DOMAIN:-_};
    return 301 https://\$host\$request_uri;
}
EOF

ln -sf "${NGINX_SITE_PATH}" "${NGINX_SITE_LINK}"
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl enable --now nginx
systemctl reload nginx

if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
  echo "[tls] ${SERVICE_NAME}.service is active."
else
  echo "[tls] WARN: ${SERVICE_NAME}.service is not active."
fi

TARGET="${TLS_DOMAIN:-${TLS_IP}}"
echo
echo "[tls] TLS reverse proxy is configured."
echo "[tls] URL: https://${TARGET}:${HTTPS_PORT}"
echo "[tls] Cert: ${CERT_CRT}"
echo "[tls] Key:  ${CERT_KEY}"
echo "[tls] Note: self-signed certificate will require trust import on clients."
