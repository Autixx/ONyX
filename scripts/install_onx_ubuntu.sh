#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Autixx/WGD_AWG_fix_multihop.git}"
GIT_REF="${GIT_REF:-dev}"
INSTALL_DIR="${INSTALL_DIR:-/opt/wgd-awg-multihop}"
SERVICE_NAME="${SERVICE_NAME:-onx-api}"
CONFIG_DIR="${CONFIG_DIR:-/etc/onx}"
ENV_FILE_NAME="${ENV_FILE_NAME:-onx.env}"
VENV_DIR_NAME="${VENV_DIR_NAME:-.venv-onx}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
BIND_PORT="${BIND_PORT:-8081}"
ENABLE_TLS_OPENSSL="${ENABLE_TLS_OPENSSL:-false}"
TLS_LOCAL_BIND="${TLS_LOCAL_BIND:-true}"
TLS_DOMAIN="${TLS_DOMAIN:-}"
TLS_IP="${TLS_IP:-}"
TLS_CERT_DAYS="${TLS_CERT_DAYS:-825}"
TLS_HTTPS_PORT="${TLS_HTTPS_PORT:-443}"
TLS_FORCE_REGEN="${TLS_FORCE_REGEN:-false}"

INSTALL_POSTGRES="${INSTALL_POSTGRES:-true}"
CONFIGURE_LOCAL_POSTGRES="${CONFIGURE_LOCAL_POSTGRES:-true}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-onx}"
POSTGRES_USER="${POSTGRES_USER:-onx}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
ONX_MASTER_KEY="${ONX_MASTER_KEY:-}"
ONX_DEBUG="${ONX_DEBUG:-false}"

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/install_onx_ubuntu.sh [options]

Options:
  --repo-url <url>              Git repository URL
  --ref <branch|tag|sha>        Git ref to checkout (default: dev)
  --install-dir <path>          Install directory (default: /opt/wgd-awg-multihop)
  --service-name <name>         systemd service name (default: onx-api)
  --config-dir <path>           ONX config directory (default: /etc/onx)
  --env-file-name <name>        Environment filename in config dir (default: onx.env)
  --venv-dir-name <name>        Venv directory under install dir (default: .venv-onx)
  --bind-host <ip>              ONX API bind host (default: 127.0.0.1)
  --bind-port <port>            ONX API bind port (default: 8081)
  --enable-tls-openssl          Configure nginx + OpenSSL self-signed HTTPS for ONX
  --tls-domain <name>           TLS certificate CN/SAN DNS name
  --tls-ip <addr>               TLS certificate SAN IP (recommended: server public IP)
  --tls-cert-days <num>         self-signed cert validity days (default: 825)
  --tls-https-port <port>       nginx HTTPS listen port (default: 443)
  --tls-force                   Regenerate certificate even if it already exists
  --no-tls-local-bind           Keep ONX API on the requested bind host instead of forcing 127.0.0.1
  --no-install-postgres         Skip postgresql package install
  --no-configure-local-postgres Do not create local db/user via postgres superuser
  --postgres-host <host>        Postgres host (default: 127.0.0.1)
  --postgres-port <port>        Postgres port (default: 5432)
  --postgres-db <name>          Postgres database name (default: onx)
  --postgres-user <name>        Postgres user name (default: onx)
  --postgres-password <pass>    Postgres user password (auto-generated if empty)
  --onx-master-key <value>      ONX master key (auto-generated if empty)
  --onx-debug <true|false>      ONX debug mode (default: false)
  -h, --help                    Show help
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

validate_name() {
  local value="$1"
  [[ "${value}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]
}

sync_git_checkout() {
  local repo_url="$1"
  local git_ref="$2"
  local target_dir="$3"

  if [[ -d "${target_dir}/.git" ]]; then
    git -C "${target_dir}" fetch --all --tags --prune
  else
    mkdir -p "$(dirname "${target_dir}")"
    git clone "${repo_url}" "${target_dir}"
  fi

  if git -C "${target_dir}" rev-parse --verify --quiet "origin/${git_ref}" >/dev/null; then
    git -C "${target_dir}" checkout -B "${git_ref}" "origin/${git_ref}"
  else
    git -C "${target_dir}" checkout "${git_ref}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --ref)
      GIT_REF="$2"
      shift 2
      ;;
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
    --venv-dir-name)
      VENV_DIR_NAME="$2"
      shift 2
      ;;
    --bind-host)
      BIND_HOST="$2"
      shift 2
      ;;
    --bind-port)
      BIND_PORT="$2"
      shift 2
      ;;
    --enable-tls-openssl)
      ENABLE_TLS_OPENSSL="true"
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
    --no-tls-local-bind)
      TLS_LOCAL_BIND="false"
      shift 1
      ;;
    --no-install-postgres)
      INSTALL_POSTGRES="false"
      shift 1
      ;;
    --no-configure-local-postgres)
      CONFIGURE_LOCAL_POSTGRES="false"
      shift 1
      ;;
    --postgres-host)
      POSTGRES_HOST="$2"
      shift 2
      ;;
    --postgres-port)
      POSTGRES_PORT="$2"
      shift 2
      ;;
    --postgres-db)
      POSTGRES_DB="$2"
      shift 2
      ;;
    --postgres-user)
      POSTGRES_USER="$2"
      shift 2
      ;;
    --postgres-password)
      POSTGRES_PASSWORD="$2"
      shift 2
      ;;
    --onx-master-key)
      ONX_MASTER_KEY="$2"
      shift 2
      ;;
    --onx-debug)
      ONX_DEBUG="$2"
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

command -v apt-get >/dev/null 2>&1 || fail "This installer supports apt-based systems only."
validate_port "${BIND_PORT}" || fail "Invalid bind port: ${BIND_PORT}"
validate_port "${POSTGRES_PORT}" || fail "Invalid postgres port: ${POSTGRES_PORT}"
validate_port "${TLS_HTTPS_PORT}" || fail "Invalid TLS https port: ${TLS_HTTPS_PORT}"
validate_bool "${ONX_DEBUG}" || fail "--onx-debug must be true or false."
validate_bool "${ENABLE_TLS_OPENSSL}" || fail "TLS flag must be true or false."
validate_bool "${TLS_LOCAL_BIND}" || fail "TLS local bind flag must be true or false."
validate_bool "${TLS_FORCE_REGEN}" || fail "TLS force flag must be true or false."
validate_name "${POSTGRES_DB}" || fail "Invalid postgres db name: ${POSTGRES_DB}"
validate_name "${POSTGRES_USER}" || fail "Invalid postgres user name: ${POSTGRES_USER}"
if [[ "${POSTGRES_PASSWORD}" == *"'"* ]]; then
  fail "Postgres password must not contain single quote (')."
fi
[[ "${TLS_CERT_DAYS}" =~ ^[0-9]+$ ]] || fail "tls-cert-days must be a positive integer."
(( TLS_CERT_DAYS >= 1 )) || fail "tls-cert-days must be >= 1."

if [[ -z "${POSTGRES_PASSWORD}" ]]; then
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi
if [[ -z "${ONX_MASTER_KEY}" ]]; then
  ONX_MASTER_KEY="$(openssl rand -hex 32)"
fi

ENV_FILE_PATH="${CONFIG_DIR}/${ENV_FILE_NAME}"
VENV_DIR="${INSTALL_DIR}/${VENV_DIR_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TLS_UPSTREAM_HOST="${BIND_HOST}"

if [[ "${ENABLE_TLS_OPENSSL}" == "true" && "${TLS_LOCAL_BIND}" == "true" ]]; then
  BIND_HOST="127.0.0.1"
fi
if [[ "${BIND_HOST}" == "0.0.0.0" ]]; then
  TLS_UPSTREAM_HOST="127.0.0.1"
elif [[ "${BIND_HOST}" == "::" ]]; then
  TLS_UPSTREAM_HOST="::1"
else
  TLS_UPSTREAM_HOST="${BIND_HOST}"
fi

echo "[1/9] Installing OS dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  git \
  openssl \
  python3 \
  python3-dev \
  python3-venv \
  python3-pip \
  build-essential \
  libffi-dev \
  libssl-dev

if [[ "${INSTALL_POSTGRES}" == "true" ]]; then
  apt-get install -y postgresql postgresql-contrib libpq-dev
  systemctl enable --now postgresql || true
fi

echo "[2/9] Fetching project source..."
sync_git_checkout "${REPO_URL}" "${GIT_REF}" "${INSTALL_DIR}"
[[ -f "${INSTALL_DIR}/requirements-onx.txt" ]] || fail "requirements-onx.txt not found in ${INSTALL_DIR}"

echo "[3/9] Preparing ONX config and environment..."
mkdir -p "${CONFIG_DIR}"
chmod 700 "${CONFIG_DIR}"

if [[ "${CONFIGURE_LOCAL_POSTGRES}" == "true" && ( "${POSTGRES_HOST}" == "127.0.0.1" || "${POSTGRES_HOST}" == "localhost" ) ]]; then
  echo "[4/9] Configuring local PostgreSQL role/database..."
  systemctl enable --now postgresql || true
  command -v psql >/dev/null 2>&1 || fail "psql is not installed but local postgres configuration is enabled."
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}';"
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';"
  fi
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"
  fi
fi

DB_URL="$(python3 - "${POSTGRES_USER}" "${POSTGRES_PASSWORD}" "${POSTGRES_HOST}" "${POSTGRES_PORT}" "${POSTGRES_DB}" <<'PY'
import sys
from urllib.parse import quote

user, password, host, port, db = sys.argv[1:]
print(f"postgresql+psycopg://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db)}")
PY
)"

cat > "${ENV_FILE_PATH}" <<EOF
# ONX runtime environment
ONX_APP_NAME=ONX API
ONX_APP_VERSION=0.1.0-alpha
ONX_DEBUG=${ONX_DEBUG}
ONX_API_PREFIX=/api/v1
ONX_DATABASE_URL=${DB_URL}
ONX_MASTER_KEY=${ONX_MASTER_KEY}

# Client routing auth: disabled | token | jwt | token_or_jwt
ONX_CLIENT_API_AUTH_MODE=disabled
ONX_CLIENT_API_TOKENS=
ONX_CLIENT_API_JWT_SECRET=
ONX_CLIENT_API_JWT_ISSUER=
ONX_CLIENT_API_JWT_AUDIENCE=

# Optional tuning
ONX_WORKER_POLL_INTERVAL_SECONDS=2
ONX_WORKER_LEASE_SECONDS=300
ONX_PROBE_SCHEDULER_ENABLED=true
ONX_PROBE_SCHEDULER_INTERVAL_SECONDS=30
EOF
chmod 600 "${ENV_FILE_PATH}"

echo "[5/9] Creating Python venv..."
python3 -m venv "${VENV_DIR}"

echo "[6/9] Installing Python dependencies..."
"${VENV_DIR}/bin/python3" -m pip install --upgrade pip wheel setuptools
"${VENV_DIR}/bin/python3" -m pip install -r "${INSTALL_DIR}/requirements-onx.txt"

echo "[7/9] Running migrations..."
(
  cd "${INSTALL_DIR}"
  set -a
  source "${ENV_FILE_PATH}"
  set +a
  "${VENV_DIR}/bin/python3" -m alembic -c alembic.ini upgrade head
)

echo "[8/9] Installing systemd service..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=ONX Control Plane API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE_PATH}
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_DIR}/bin/uvicorn onx.api.app:app --host ${BIND_HOST} --port ${BIND_PORT}
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

echo "[9/9] Enabling and starting service..."
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

if [[ "${ENABLE_TLS_OPENSSL}" == "true" ]]; then
  echo "[tls] Configuring nginx HTTPS reverse proxy for ONX..."
  TLS_ARGS=(
    "--service-name" "${SERVICE_NAME}"
    "--upstream-host" "${TLS_UPSTREAM_HOST}"
    "--upstream-port" "${BIND_PORT}"
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

echo
echo "ONX install complete."
echo "Service:  ${SERVICE_NAME}.service"
echo "Env file: ${ENV_FILE_PATH}"
echo "Status:   systemctl status ${SERVICE_NAME}.service --no-pager"
echo "Logs:     journalctl -u ${SERVICE_NAME}.service -f"
echo "Health:   curl -fsS http://${BIND_HOST}:${BIND_PORT}/api/v1/health"
if [[ "${ENABLE_TLS_OPENSSL}" == "true" ]]; then
  echo "HTTPS:    https://${TLS_DOMAIN:-${TLS_IP:-<server-ip>}}:${TLS_HTTPS_PORT}/api/v1/health"
fi
echo
echo "If needed, edit auth/limits in ${ENV_FILE_PATH} and restart service:"
echo "  sudo systemctl restart ${SERVICE_NAME}.service"
