#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/onyx}"
SERVICE_NAME="${SERVICE_NAME:-onx-api}"
CONFIG_DIR="${CONFIG_DIR:-/etc/onx}"
ENV_FILE_NAME="${ENV_FILE_NAME:-onx.env}"
GIT_REF="${GIT_REF:-main}"
VENV_DIR_NAME="${VENV_DIR_NAME:-.venv-onx}"
REFRESH_TLS_OPENSSL="${REFRESH_TLS_OPENSSL:-false}"
TLS_DOMAIN="${TLS_DOMAIN:-}"
TLS_IP="${TLS_IP:-}"
TLS_CERT_DAYS="${TLS_CERT_DAYS:-825}"
TLS_HTTPS_PORT="${TLS_HTTPS_PORT:-443}"
TLS_FORCE_REGEN="${TLS_FORCE_REGEN:-false}"
TLS_UPSTREAM_HOST="${TLS_UPSTREAM_HOST:-127.0.0.1}"
TLS_UPSTREAM_PORT="${TLS_UPSTREAM_PORT:-8081}"

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/update_onx_ubuntu.sh [options]

Options:
  --install-dir <path>      ONyX project directory (default: /opt/onyx)
  --service-name <name>     systemd service name (default: onx-api)
  --config-dir <path>       ONX config directory (default: /etc/onx)
  --env-file-name <name>    env filename in config dir (default: onx.env)
  --ref <branch|tag|sha>    git ref to pull (default: main)
  --venv-dir-name <name>    venv directory under install dir (default: .venv-onx)
  --refresh-tls-openssl     Re-run nginx/OpenSSL TLS setup for ONX and reload nginx
  --tls-domain <name>       TLS certificate CN/SAN DNS name
  --tls-ip <addr>           TLS certificate SAN IP
  --tls-cert-days <num>     self-signed cert validity days (default: 825)
  --tls-https-port <port>   nginx HTTPS port (default: 443)
  --tls-force               Regenerate certificate even if it already exists
  --tls-upstream-host <h>   ONX upstream host for nginx proxy (default: 127.0.0.1)
  --tls-upstream-port <p>   ONX upstream port for nginx proxy (default: 8081)
  -h, --help                Show help
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

validate_bool() {
  case "$1" in
    true|false) return 0 ;;
    *) return 1 ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --config-dir)
      CONFIG_DIR="$2"
      shift 2
      ;;
    --env-file-name)
      ENV_FILE_NAME="$2"
      shift 2
      ;;
    --ref)
      GIT_REF="$2"
      shift 2
      ;;
    --venv-dir-name)
      VENV_DIR_NAME="$2"
      shift 2
      ;;
    --refresh-tls-openssl)
      REFRESH_TLS_OPENSSL="true"
      shift 1
      ;;
    --tls-domain)
      TLS_DOMAIN="$2"
      shift 2
      ;;
    --tls-ip)
      TLS_IP="$2"
      shift 2
      ;;
    --tls-cert-days)
      TLS_CERT_DAYS="$2"
      shift 2
      ;;
    --tls-https-port)
      TLS_HTTPS_PORT="$2"
      shift 2
      ;;
    --tls-force)
      TLS_FORCE_REGEN="true"
      shift 1
      ;;
    --tls-upstream-host)
      TLS_UPSTREAM_HOST="$2"
      shift 2
      ;;
    --tls-upstream-port)
      TLS_UPSTREAM_PORT="$2"
      shift 2
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

validate_bool "${REFRESH_TLS_OPENSSL}" || fail "refresh-tls-openssl flag must be true or false."
validate_bool "${TLS_FORCE_REGEN}" || fail "tls-force flag must be true or false."
validate_port "${TLS_HTTPS_PORT}" || fail "Invalid tls https port: ${TLS_HTTPS_PORT}"
validate_port "${TLS_UPSTREAM_PORT}" || fail "Invalid tls upstream port: ${TLS_UPSTREAM_PORT}"
[[ "${TLS_CERT_DAYS}" =~ ^[0-9]+$ ]] || fail "tls-cert-days must be a positive integer."
(( TLS_CERT_DAYS >= 1 )) || fail "tls-cert-days must be >= 1."

ENV_FILE_PATH="${CONFIG_DIR}/${ENV_FILE_NAME}"
VENV_DIR="${INSTALL_DIR}/${VENV_DIR_NAME}"
LAUNCHER_PATH="/usr/local/bin/onx"
ADMIN_WEB_AUTH_INFO_PATH="${CONFIG_DIR}/admin-web-auth.txt"

[[ -d "${INSTALL_DIR}/.git" ]] || fail "Install dir is not a git repo: ${INSTALL_DIR}"
[[ -f "${INSTALL_DIR}/requirements-onx.txt" ]] || fail "requirements-onx.txt not found in ${INSTALL_DIR}"
[[ -f "${ENV_FILE_PATH}" ]] || fail "ONX env file not found: ${ENV_FILE_PATH}"
[[ -x "${VENV_DIR}/bin/python3" ]] || fail "ONX venv python not found: ${VENV_DIR}/bin/python3"

echo "[1/6] Pulling source (ref: ${GIT_REF})..."
git -C "${INSTALL_DIR}" fetch --all --tags --prune \
  || fail "git fetch failed — check network and remote credentials."

if git -C "${INSTALL_DIR}" rev-parse --verify --quiet "origin/${GIT_REF}" >/dev/null 2>&1; then
  git -C "${INSTALL_DIR}" checkout -B "${GIT_REF}" "origin/${GIT_REF}"
  git -C "${INSTALL_DIR}" reset --hard "origin/${GIT_REF}"
else
  git -C "${INSTALL_DIR}" checkout "${GIT_REF}"
  git -C "${INSTALL_DIR}" reset --hard "${GIT_REF}"
fi
echo "  → $(git -C "${INSTALL_DIR}" log --oneline -1)"

echo "[2/6] Building frontend..."
WEB_ADMIN_DIR="${INSTALL_DIR}/apps/web-admin"
if command -v npm &>/dev/null && [[ -f "${WEB_ADMIN_DIR}/package.json" ]]; then
  npm ci --prefix "${WEB_ADMIN_DIR}" --silent
  npm run build --prefix "${WEB_ADMIN_DIR}"
  echo "  → Frontend built."
else
  echo "  → npm not found, skipping frontend build (pre-built dist will be used)."
fi

echo "[3/6] Updating Python dependencies..."
"${VENV_DIR}/bin/python3" -m pip install --upgrade pip wheel setuptools
"${VENV_DIR}/bin/python3" -m pip install -r "${INSTALL_DIR}/requirements-onx.txt"

cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_DIR}/bin/python3" "${INSTALL_DIR}/scripts/onx_admin_menu.py" "\$@"
EOF
chmod 755 "${LAUNCHER_PATH}"

echo "[3.5/6] Backfilling web auth/static-ui defaults..."
ADMIN_WEB_BOOTSTRAP_USERNAME="$(awk -F= '/^ONX_ADMIN_WEB_BOOTSTRAP_USERNAME=/{print $2}' "${ENV_FILE_PATH}" | tail -n1)"
ADMIN_WEB_BOOTSTRAP_PASSWORD="$(awk -F= '/^ONX_ADMIN_WEB_BOOTSTRAP_PASSWORD=/{print $2}' "${ENV_FILE_PATH}" | tail -n1)"
if [[ -z "${ADMIN_WEB_BOOTSTRAP_USERNAME}" ]]; then
  ADMIN_WEB_BOOTSTRAP_USERNAME="admin"
fi
if [[ -z "${ADMIN_WEB_BOOTSTRAP_PASSWORD}" ]]; then
  ADMIN_WEB_BOOTSTRAP_PASSWORD="onx-web-$(openssl rand -hex 12)"
fi
if ! grep -q '^ONX_WEB_UI_ENABLED=' "${ENV_FILE_PATH}"; then
  echo 'ONX_WEB_UI_ENABLED=true' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_WEB_UI_DIR=' "${ENV_FILE_PATH}"; then
  echo "ONX_WEB_UI_DIR=${INSTALL_DIR}/apps/web-admin/dist" >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_WEB_UI_PATH=' "${ENV_FILE_PATH}"; then
  echo 'ONX_WEB_UI_PATH=/' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_PUBLIC_BASE_URL=' "${ENV_FILE_PATH}"; then
  BASE_IP="${TLS_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
  if [[ -n "${TLS_DOMAIN}" ]]; then
    if [[ "${TLS_HTTPS_PORT}" == "443" ]]; then
      echo "ONX_PUBLIC_BASE_URL=https://${TLS_DOMAIN}" >> "${ENV_FILE_PATH}"
    else
      echo "ONX_PUBLIC_BASE_URL=https://${TLS_DOMAIN}:${TLS_HTTPS_PORT}" >> "${ENV_FILE_PATH}"
    fi
  elif [[ -n "${BASE_IP}" ]]; then
    if [[ "${REFRESH_TLS_OPENSSL}" == "true" ]]; then
      if [[ "${TLS_HTTPS_PORT}" == "443" ]]; then
        echo "ONX_PUBLIC_BASE_URL=https://${BASE_IP}" >> "${ENV_FILE_PATH}"
      else
        echo "ONX_PUBLIC_BASE_URL=https://${BASE_IP}:${TLS_HTTPS_PORT}" >> "${ENV_FILE_PATH}"
      fi
    else
      echo "ONX_PUBLIC_BASE_URL=http://${BASE_IP}:8081" >> "${ENV_FILE_PATH}"
    fi
  fi
fi
if ! grep -q '^ONX_ADMIN_WEB_AUTH_ENABLED=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_AUTH_ENABLED=true' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_BOOTSTRAP_USERNAME=' "${ENV_FILE_PATH}"; then
  echo "ONX_ADMIN_WEB_BOOTSTRAP_USERNAME=${ADMIN_WEB_BOOTSTRAP_USERNAME}" >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_BOOTSTRAP_PASSWORD=' "${ENV_FILE_PATH}"; then
  echo "ONX_ADMIN_WEB_BOOTSTRAP_PASSWORD=${ADMIN_WEB_BOOTSTRAP_PASSWORD}" >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_BOOTSTRAP_ROLES=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_BOOTSTRAP_ROLES=admin' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_SESSION_COOKIE_NAME=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_SESSION_COOKIE_NAME=onx_session' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_SESSION_TTL_SECONDS=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_SESSION_TTL_SECONDS=43200' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_SECURE_COOKIES=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_SECURE_COOKIES=true' >> "${ENV_FILE_PATH}"
fi
if ! grep -q '^ONX_ADMIN_WEB_COOKIE_SAME_SITE=' "${ENV_FILE_PATH}"; then
  echo 'ONX_ADMIN_WEB_COOKIE_SAME_SITE=lax' >> "${ENV_FILE_PATH}"
fi
chmod 600 "${ENV_FILE_PATH}"
if [[ ! -f "${ADMIN_WEB_AUTH_INFO_PATH}" ]]; then
  {
    echo "# Generated by update_onx_ubuntu.sh"
    echo "enabled=true"
    echo "username=${ADMIN_WEB_BOOTSTRAP_USERNAME}"
    echo "password=${ADMIN_WEB_BOOTSTRAP_PASSWORD}"
    echo "cookie_name=onx_session"
  } > "${ADMIN_WEB_AUTH_INFO_PATH}"
  chmod 600 "${ADMIN_WEB_AUTH_INFO_PATH}"
fi

echo "[4/6] Applying migrations..."
(
  cd "${INSTALL_DIR}"
  set -a
  source "${ENV_FILE_PATH}"
  set +a
  "${VENV_DIR}/bin/python3" -m alembic -c alembic.ini upgrade head
)

echo "[5/6] Restarting service..."
systemctl daemon-reload
systemctl restart "${SERVICE_NAME}.service"

if [[ "${REFRESH_TLS_OPENSSL}" == "true" ]]; then
  echo "[tls] Refreshing nginx/OpenSSL TLS setup..."
  TLS_ARGS=(
    "--service-name" "${SERVICE_NAME}"
    "--upstream-host" "${TLS_UPSTREAM_HOST}"
    "--upstream-port" "${TLS_UPSTREAM_PORT}"
    "--https-port" "${TLS_HTTPS_PORT}"
    "--cert-days" "${TLS_CERT_DAYS}"
  )
  if [[ -n "${TLS_DOMAIN}" ]]; then
    TLS_ARGS+=("--domain" "${TLS_DOMAIN}")
  fi
  if [[ -n "${TLS_IP}" ]]; then
    TLS_ARGS+=("--ip" "${TLS_IP}")
  fi
  if [[ "${TLS_FORCE_REGEN}" == "true" ]]; then
    TLS_ARGS+=("--force")
  fi
  bash "${INSTALL_DIR}/scripts/setup_onx_tls_openssl.sh" "${TLS_ARGS[@]}"
fi

echo "[6/6] Done."
echo "Status: systemctl status ${SERVICE_NAME}.service --no-pager"
echo "Logs:   journalctl -u ${SERVICE_NAME}.service -f"
