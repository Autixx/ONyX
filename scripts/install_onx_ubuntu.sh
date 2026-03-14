#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Autixx/ONyX.git}"
GIT_REF="${GIT_REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/onyx}"
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
RUN_ALPHA_SMOKE="${RUN_ALPHA_SMOKE:-false}"
SMOKE_BASE_URL="${SMOKE_BASE_URL:-}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-10}"
SMOKE_EXPECT_AUTH="${SMOKE_EXPECT_AUTH:-false}"
SMOKE_CHECK_RATE_LIMIT="${SMOKE_CHECK_RATE_LIMIT:-false}"
SMOKE_BEARER_TOKEN="${SMOKE_BEARER_TOKEN:-}"
CLIENT_API_AUTH_MODE="${CLIENT_API_AUTH_MODE:-token}"
CLIENT_API_TOKENS="${CLIENT_API_TOKENS:-}"
CLIENT_API_JWT_SECRET="${CLIENT_API_JWT_SECRET:-}"
CLIENT_API_JWT_ISSUER="${CLIENT_API_JWT_ISSUER:-onyx-control}"
CLIENT_API_JWT_AUDIENCE="${CLIENT_API_JWT_AUDIENCE:-onyx-client}"
ADMIN_API_AUTH_MODE="${ADMIN_API_AUTH_MODE:-token}"
ADMIN_API_TOKENS="${ADMIN_API_TOKENS:-}"
ADMIN_API_JWT_SECRET="${ADMIN_API_JWT_SECRET:-}"
ADMIN_API_JWT_ISSUER="${ADMIN_API_JWT_ISSUER:-onyx-admin}"
ADMIN_API_JWT_AUDIENCE="${ADMIN_API_JWT_AUDIENCE:-onyx-admin-api}"
ADMIN_WEB_AUTH_ENABLED="${ADMIN_WEB_AUTH_ENABLED:-true}"
ADMIN_WEB_BOOTSTRAP_USERNAME="${ADMIN_WEB_BOOTSTRAP_USERNAME:-admin}"
ADMIN_WEB_BOOTSTRAP_PASSWORD="${ADMIN_WEB_BOOTSTRAP_PASSWORD:-}"
WEB_UI_ENABLED="${WEB_UI_ENABLED:-true}"
WEB_UI_DIR="${WEB_UI_DIR:-}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

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
  --ref <branch|tag|sha>        Git ref to checkout (default: main)
  --install-dir <path>          Install directory (default: /opt/onyx)
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
  --run-alpha-smoke             Run ONX alpha smoke check after service start
  --smoke-base-url <url>        Override smoke base URL (default: local ONX API)
  --smoke-timeout <sec>         Smoke HTTP timeout in seconds (default: 10)
  --smoke-expect-auth           Expect 401 on unauthenticated client-routing requests
  --smoke-check-rate-limit      Expect 429/Retry-After on repeated session-rebind
  --smoke-bearer-token <token>  Bearer token or JWT for strict smoke mode
  --client-auth-mode <mode>     disabled | token | jwt | token_or_jwt (default: token)
  --client-api-tokens <csv>     Static bearer token list for client-routing auth
  --client-api-jwt-secret <v>   HS256 JWT secret for client-routing auth
  --client-api-jwt-issuer <v>   JWT issuer hint written to env (default: onyx-control)
  --client-api-jwt-audience <v> JWT audience hint written to env (default: onyx-client)
  --admin-auth-mode <mode>      disabled | token | jwt | token_or_jwt (default: token)
  --admin-api-tokens <csv>      Static bearer token list for admin/control-plane auth
  --admin-api-jwt-secret <v>    HS256 JWT secret for admin/control-plane auth
  --admin-api-jwt-issuer <v>    JWT issuer hint written to env (default: onyx-admin)
  --admin-api-jwt-audience <v>  JWT audience hint written to env (default: onyx-admin-api)
  --admin-web-auth-enabled      Enable browser login/session auth (default: true)
  --admin-web-bootstrap-username <v>
                                Initial admin web-auth username (default: admin)
  --admin-web-bootstrap-password <v>
                                Initial admin web-auth password (auto-generated if empty)
  --web-ui-enabled              Enable same-origin static UI hosting scaffold (default: true)
  --web-ui-dir <path>           Static UI build directory (default: /opt/onyx/apps/web-admin/dist)
  --public-base-url <url>       Public ONyX base URL for node agents and future clients
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
    --run-alpha-smoke)
      RUN_ALPHA_SMOKE="true"
      shift 1
      ;;
    --smoke-base-url)
      SMOKE_BASE_URL="$2"
      shift 2
      ;;
    --smoke-timeout)
      SMOKE_TIMEOUT="$2"
      shift 2
      ;;
    --smoke-expect-auth)
      SMOKE_EXPECT_AUTH="true"
      shift 1
      ;;
    --smoke-check-rate-limit)
      SMOKE_CHECK_RATE_LIMIT="true"
      shift 1
      ;;
    --smoke-bearer-token)
      SMOKE_BEARER_TOKEN="$2"
      shift 2
      ;;
    --client-auth-mode)
      CLIENT_API_AUTH_MODE="$2"
      shift 2
      ;;
    --client-api-tokens)
      CLIENT_API_TOKENS="$2"
      shift 2
      ;;
    --client-api-jwt-secret)
      CLIENT_API_JWT_SECRET="$2"
      shift 2
      ;;
    --client-api-jwt-issuer)
      CLIENT_API_JWT_ISSUER="$2"
      shift 2
      ;;
    --client-api-jwt-audience)
      CLIENT_API_JWT_AUDIENCE="$2"
      shift 2
      ;;
    --admin-auth-mode)
      ADMIN_API_AUTH_MODE="$2"
      shift 2
      ;;
    --admin-api-tokens)
      ADMIN_API_TOKENS="$2"
      shift 2
      ;;
    --admin-api-jwt-secret)
      ADMIN_API_JWT_SECRET="$2"
      shift 2
      ;;
    --admin-api-jwt-issuer)
      ADMIN_API_JWT_ISSUER="$2"
      shift 2
      ;;
    --admin-api-jwt-audience)
      ADMIN_API_JWT_AUDIENCE="$2"
      shift 2
      ;;
    --admin-web-auth-enabled)
      ADMIN_WEB_AUTH_ENABLED="true"
      shift 1
      ;;
    --admin-web-bootstrap-username)
      ADMIN_WEB_BOOTSTRAP_USERNAME="$2"
      shift 2
      ;;
    --admin-web-bootstrap-password)
      ADMIN_WEB_BOOTSTRAP_PASSWORD="$2"
      shift 2
      ;;
    --web-ui-enabled)
      WEB_UI_ENABLED="true"
      shift 1
      ;;
    --web-ui-dir)
      WEB_UI_DIR="$2"
      shift 2
      ;;
    --public-base-url)
      PUBLIC_BASE_URL="$2"
      shift 2
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
validate_bool "${RUN_ALPHA_SMOKE}" || fail "run-alpha-smoke flag must be true or false."
validate_bool "${SMOKE_EXPECT_AUTH}" || fail "smoke-expect-auth flag must be true or false."
validate_bool "${SMOKE_CHECK_RATE_LIMIT}" || fail "smoke-check-rate-limit flag must be true or false."
validate_bool "${ADMIN_WEB_AUTH_ENABLED}" || fail "admin-web-auth-enabled flag must be true or false."
validate_bool "${WEB_UI_ENABLED}" || fail "web-ui-enabled flag must be true or false."
validate_name "${POSTGRES_DB}" || fail "Invalid postgres db name: ${POSTGRES_DB}"
validate_name "${POSTGRES_USER}" || fail "Invalid postgres user name: ${POSTGRES_USER}"
if [[ "${POSTGRES_PASSWORD}" == *"'"* ]]; then
  fail "Postgres password must not contain single quote (')."
fi
[[ "${TLS_CERT_DAYS}" =~ ^[0-9]+$ ]] || fail "tls-cert-days must be a positive integer."
(( TLS_CERT_DAYS >= 1 )) || fail "tls-cert-days must be >= 1."
[[ "${SMOKE_TIMEOUT}" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "smoke-timeout must be a positive number."
case "${CLIENT_API_AUTH_MODE}" in
  disabled|token|jwt|token_or_jwt) ;;
  *) fail "client-auth-mode must be one of: disabled, token, jwt, token_or_jwt" ;;
esac
case "${ADMIN_API_AUTH_MODE}" in
  disabled|token|jwt|token_or_jwt) ;;
  *) fail "admin-auth-mode must be one of: disabled, token, jwt, token_or_jwt" ;;
esac
if [[ -z "${WEB_UI_DIR}" ]]; then
  WEB_UI_DIR="${INSTALL_DIR}/apps/web-admin/dist"
fi
if [[ -z "${PUBLIC_BASE_URL}" ]]; then
  if [[ "${ENABLE_TLS_OPENSSL}" == "true" ]]; then
    PUBLIC_HOST="${TLS_DOMAIN:-${TLS_IP:-}}"
    if [[ -n "${PUBLIC_HOST}" ]]; then
      if [[ "${TLS_HTTPS_PORT}" == "443" ]]; then
        PUBLIC_BASE_URL="https://${PUBLIC_HOST}"
      else
        PUBLIC_BASE_URL="https://${PUBLIC_HOST}:${TLS_HTTPS_PORT}"
      fi
    fi
  fi
  if [[ -z "${PUBLIC_BASE_URL}" ]]; then
    LOCAL_PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -n "${LOCAL_PRIMARY_IP}" ]]; then
      PUBLIC_BASE_URL="http://${LOCAL_PRIMARY_IP}:${BIND_PORT}"
    else
      PUBLIC_BASE_URL="http://127.0.0.1:${BIND_PORT}"
    fi
  fi
fi

if [[ -z "${POSTGRES_PASSWORD}" ]]; then
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi
if [[ -z "${ONX_MASTER_KEY}" ]]; then
  ONX_MASTER_KEY="$(openssl rand -hex 32)"
fi
if [[ "${CLIENT_API_AUTH_MODE}" == "token" || "${CLIENT_API_AUTH_MODE}" == "token_or_jwt" ]]; then
  if [[ -z "${CLIENT_API_TOKENS}" ]]; then
    CLIENT_API_TOKENS="onx-$(openssl rand -hex 24)"
  fi
fi
if [[ "${CLIENT_API_AUTH_MODE}" == "jwt" || "${CLIENT_API_AUTH_MODE}" == "token_or_jwt" ]]; then
  if [[ -z "${CLIENT_API_JWT_SECRET}" ]]; then
    CLIENT_API_JWT_SECRET="$(openssl rand -hex 32)"
  fi
fi
if [[ "${ADMIN_API_AUTH_MODE}" == "token" || "${ADMIN_API_AUTH_MODE}" == "token_or_jwt" ]]; then
  if [[ -z "${ADMIN_API_TOKENS}" ]]; then
    ADMIN_API_TOKENS="admin=onx-admin-$(openssl rand -hex 24)"
  fi
fi
if [[ "${ADMIN_API_AUTH_MODE}" == "jwt" || "${ADMIN_API_AUTH_MODE}" == "token_or_jwt" ]]; then
  if [[ -z "${ADMIN_API_JWT_SECRET}" ]]; then
    ADMIN_API_JWT_SECRET="$(openssl rand -hex 32)"
  fi
fi
if [[ "${ADMIN_WEB_AUTH_ENABLED}" == "true" && -z "${ADMIN_WEB_BOOTSTRAP_PASSWORD}" ]]; then
  ADMIN_WEB_BOOTSTRAP_PASSWORD="onx-web-$(openssl rand -hex 12)"
fi

ENV_FILE_PATH="${CONFIG_DIR}/${ENV_FILE_NAME}"
VENV_DIR="${INSTALL_DIR}/${VENV_DIR_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LAUNCHER_PATH="/usr/local/bin/onx"
TLS_UPSTREAM_HOST="${BIND_HOST}"
CLIENT_AUTH_INFO_PATH="${CONFIG_DIR}/client-auth.txt"
ADMIN_AUTH_INFO_PATH="${CONFIG_DIR}/admin-auth.txt"
ADMIN_WEB_AUTH_INFO_PATH="${CONFIG_DIR}/admin-web-auth.txt"

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
if [[ -z "${SMOKE_BASE_URL}" ]]; then
  SMOKE_HOST="${BIND_HOST}"
  if [[ "${SMOKE_HOST}" == "0.0.0.0" || "${SMOKE_HOST}" == "::" ]]; then
    SMOKE_HOST="127.0.0.1"
  fi
  SMOKE_BASE_URL="http://${SMOKE_HOST}:${BIND_PORT}/api/v1"
fi
if [[ -z "${SMOKE_BEARER_TOKEN}" ]]; then
  if [[ "${CLIENT_API_AUTH_MODE}" == "token" || "${CLIENT_API_AUTH_MODE}" == "token_or_jwt" ]]; then
    SMOKE_BEARER_TOKEN="${CLIENT_API_TOKENS%%,*}"
  fi
fi
if [[ -z "${ADMIN_SMOKE_BEARER_TOKEN:-}" ]]; then
  if [[ "${ADMIN_API_AUTH_MODE}" == "token" || "${ADMIN_API_AUTH_MODE}" == "token_or_jwt" ]]; then
    ADMIN_SMOKE_BEARER_TOKEN="${ADMIN_API_TOKENS%%,*}"
    ADMIN_SMOKE_BEARER_TOKEN="${ADMIN_SMOKE_BEARER_TOKEN#*=}"
  else
    ADMIN_SMOKE_BEARER_TOKEN=""
  fi
fi
if [[ "${SMOKE_EXPECT_AUTH}" == "true" && -z "${SMOKE_BEARER_TOKEN}" ]]; then
  fail "--smoke-expect-auth requires a bearer token. Provide --smoke-bearer-token or use token auth mode."
fi
if [[ "${SMOKE_CHECK_RATE_LIMIT}" == "true" && -z "${SMOKE_BEARER_TOKEN}" ]]; then
  fail "--smoke-check-rate-limit requires a bearer token. Provide --smoke-bearer-token or use token auth mode."
fi
if [[ "${RUN_ALPHA_SMOKE}" == "true" && "${ADMIN_API_AUTH_MODE}" != "disabled" && -z "${ADMIN_SMOKE_BEARER_TOKEN}" ]]; then
  fail "Admin API auth is enabled, but no admin smoke bearer token is available."
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
ONX_APP_NAME=ONX_API
ONX_APP_VERSION=0.1.0-alpha
ONX_DEBUG=${ONX_DEBUG}
ONX_API_PREFIX=/api/v1
ONX_DATABASE_URL=${DB_URL}
ONX_MASTER_KEY=${ONX_MASTER_KEY}
ONX_WEB_UI_ENABLED=${WEB_UI_ENABLED}
ONX_WEB_UI_DIR=${WEB_UI_DIR}
ONX_PUBLIC_BASE_URL=${PUBLIC_BASE_URL}

# Client routing auth: disabled | token | jwt | token_or_jwt
ONX_CLIENT_API_AUTH_MODE=${CLIENT_API_AUTH_MODE}
ONX_CLIENT_API_TOKENS=${CLIENT_API_TOKENS}
ONX_CLIENT_API_JWT_SECRET=${CLIENT_API_JWT_SECRET}
ONX_CLIENT_API_JWT_ISSUER=${CLIENT_API_JWT_ISSUER}
ONX_CLIENT_API_JWT_AUDIENCE=${CLIENT_API_JWT_AUDIENCE}

# Optional tuning
ONX_WORKER_POLL_INTERVAL_SECONDS=2
ONX_WORKER_LEASE_SECONDS=300
ONX_PROBE_SCHEDULER_ENABLED=true
ONX_PROBE_SCHEDULER_INTERVAL_SECONDS=30

# Admin API auth: disabled | token | jwt | token_or_jwt
ONX_ADMIN_API_AUTH_MODE=${ADMIN_API_AUTH_MODE}
ONX_ADMIN_API_TOKENS=${ADMIN_API_TOKENS}
ONX_ADMIN_API_JWT_SECRET=${ADMIN_API_JWT_SECRET}
ONX_ADMIN_API_JWT_ISSUER=${ADMIN_API_JWT_ISSUER}
ONX_ADMIN_API_JWT_AUDIENCE=${ADMIN_API_JWT_AUDIENCE}
ONX_ADMIN_WEB_AUTH_ENABLED=${ADMIN_WEB_AUTH_ENABLED}
ONX_ADMIN_WEB_BOOTSTRAP_USERNAME=${ADMIN_WEB_BOOTSTRAP_USERNAME}
ONX_ADMIN_WEB_BOOTSTRAP_PASSWORD=${ADMIN_WEB_BOOTSTRAP_PASSWORD}
ONX_ADMIN_WEB_BOOTSTRAP_ROLES=admin
ONX_ADMIN_WEB_SESSION_COOKIE_NAME=onx_session
ONX_ADMIN_WEB_SESSION_TTL_SECONDS=43200
ONX_ADMIN_WEB_SECURE_COOKIES=true
ONX_ADMIN_WEB_COOKIE_SAME_SITE=lax
EOF
chmod 600 "${ENV_FILE_PATH}"
{
  echo "# Generated by install_onx_ubuntu.sh"
  echo "mode=${CLIENT_API_AUTH_MODE}"
  if [[ -n "${CLIENT_API_TOKENS}" ]]; then
    CLIENT_PRIMARY_TOKEN="${CLIENT_API_TOKENS%%,*}"
    echo "tokens=${CLIENT_API_TOKENS}"
    echo "primary_token=${CLIENT_PRIMARY_TOKEN}"
  fi
  if [[ -n "${CLIENT_API_JWT_SECRET}" ]]; then
    echo "jwt_secret=${CLIENT_API_JWT_SECRET}"
  fi
  if [[ -n "${CLIENT_API_JWT_ISSUER}" ]]; then
    echo "jwt_issuer=${CLIENT_API_JWT_ISSUER}"
  fi
  if [[ -n "${CLIENT_API_JWT_AUDIENCE}" ]]; then
    echo "jwt_audience=${CLIENT_API_JWT_AUDIENCE}"
  fi
} > "${CLIENT_AUTH_INFO_PATH}"
chmod 600 "${CLIENT_AUTH_INFO_PATH}"
{
  echo "# Generated by install_onx_ubuntu.sh"
  echo "mode=${ADMIN_API_AUTH_MODE}"
  if [[ -n "${ADMIN_API_TOKENS}" ]]; then
    ADMIN_PRIMARY_ENTRY="${ADMIN_API_TOKENS%%,*}"
    ADMIN_PRIMARY_TOKEN="${ADMIN_PRIMARY_ENTRY#*=}"
    echo "tokens=${ADMIN_API_TOKENS}"
    echo "primary_token=${ADMIN_PRIMARY_TOKEN}"
  fi
  if [[ -n "${ADMIN_API_JWT_SECRET}" ]]; then
    echo "jwt_secret=${ADMIN_API_JWT_SECRET}"
  fi
  if [[ -n "${ADMIN_API_JWT_ISSUER}" ]]; then
    echo "jwt_issuer=${ADMIN_API_JWT_ISSUER}"
  fi
  if [[ -n "${ADMIN_API_JWT_AUDIENCE}" ]]; then
    echo "jwt_audience=${ADMIN_API_JWT_AUDIENCE}"
  fi
} > "${ADMIN_AUTH_INFO_PATH}"
chmod 600 "${ADMIN_AUTH_INFO_PATH}"
{
  echo "# Generated by install_onx_ubuntu.sh"
  echo "enabled=${ADMIN_WEB_AUTH_ENABLED}"
  echo "username=${ADMIN_WEB_BOOTSTRAP_USERNAME}"
  echo "password=${ADMIN_WEB_BOOTSTRAP_PASSWORD}"
  echo "cookie_name=onx_session"
} > "${ADMIN_WEB_AUTH_INFO_PATH}"
chmod 600 "${ADMIN_WEB_AUTH_INFO_PATH}"

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

echo "[8/10] Installing systemd service..."
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

echo "[9/10] Installing ONX launcher..."
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_DIR}/bin/python3" "${INSTALL_DIR}/scripts/onx_admin_menu.py" "\$@"
EOF
chmod 755 "${LAUNCHER_PATH}"

echo "[10/10] Enabling and starting service..."
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

if [[ "${RUN_ALPHA_SMOKE}" == "true" ]]; then
  echo "[smoke] Waiting for ONX API health..."
  HEALTH_URL="${SMOKE_BASE_URL%/}/health"
  for _ in $(seq 1 30); do
    if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  curl -fsS "${HEALTH_URL}" >/dev/null 2>&1 || fail "ONX API health check failed before smoke run: ${HEALTH_URL}"

  SMOKE_ARGS=(
    "--base-url" "${SMOKE_BASE_URL}"
    "--timeout" "${SMOKE_TIMEOUT}"
  )
  if [[ -n "${SMOKE_BEARER_TOKEN}" ]]; then
    SMOKE_ARGS+=("--client-bearer-token" "${SMOKE_BEARER_TOKEN}")
  fi
  if [[ -n "${ADMIN_SMOKE_BEARER_TOKEN}" ]]; then
    SMOKE_ARGS+=("--admin-bearer-token" "${ADMIN_SMOKE_BEARER_TOKEN}")
  fi
  if [[ "${SMOKE_EXPECT_AUTH}" == "true" ]]; then
    SMOKE_ARGS+=("--expect-auth")
  fi
  if [[ "${SMOKE_CHECK_RATE_LIMIT}" == "true" ]]; then
    SMOKE_ARGS+=("--check-rate-limit")
  fi

  echo "[smoke] Running ONX alpha smoke..."
  (
    cd "${INSTALL_DIR}"
    "${VENV_DIR}/bin/python3" scripts/onx_alpha_smoke.py "${SMOKE_ARGS[@]}"
  )
fi

echo
echo "ONX install complete."
echo "Service:  ${SERVICE_NAME}.service"
echo "Env file: ${ENV_FILE_PATH}"
echo "Auth:     ${CLIENT_AUTH_INFO_PATH}"
echo "Admin:    ${ADMIN_AUTH_INFO_PATH}"
echo "Web auth: ${ADMIN_WEB_AUTH_INFO_PATH}"
echo "Status:   systemctl status ${SERVICE_NAME}.service --no-pager"
echo "Logs:     journalctl -u ${SERVICE_NAME}.service -f"
echo "Health:   curl -fsS http://${BIND_HOST}:${BIND_PORT}/api/v1/health"
echo "Menu:     onx"
if [[ "${ENABLE_TLS_OPENSSL}" == "true" ]]; then
  echo "HTTPS:    https://${TLS_DOMAIN:-${TLS_IP:-<server-ip>}}:${TLS_HTTPS_PORT}/api/v1/health"
fi
echo
echo "If needed, edit auth/limits in ${ENV_FILE_PATH} and restart service:"
echo "  sudo systemctl restart ${SERVICE_NAME}.service"
if [[ "${CLIENT_API_AUTH_MODE}" != "disabled" ]]; then
  echo "Client auth mode: ${CLIENT_API_AUTH_MODE}"
  echo "Client auth file: ${CLIENT_AUTH_INFO_PATH}"
fi
if [[ "${ADMIN_API_AUTH_MODE}" != "disabled" ]]; then
  echo "Admin auth mode:  ${ADMIN_API_AUTH_MODE}"
  echo "Admin auth file:  ${ADMIN_AUTH_INFO_PATH}"
fi
if [[ "${ADMIN_WEB_AUTH_ENABLED}" == "true" ]]; then
  echo "Web login file:   ${ADMIN_WEB_AUTH_INFO_PATH}"
fi
