#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/wgd-awg-multihop}"
SERVICE_NAME="${SERVICE_NAME:-onx-api}"
CONFIG_DIR="${CONFIG_DIR:-/etc/onx}"
ENV_FILE_NAME="${ENV_FILE_NAME:-onx.env}"
GIT_REF="${GIT_REF:-dev}"
VENV_DIR_NAME="${VENV_DIR_NAME:-.venv-onx}"

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/update_onx_ubuntu.sh [options]

Options:
  --install-dir <path>      ONX project directory (default: /opt/wgd-awg-multihop)
  --service-name <name>     systemd service name (default: onx-api)
  --config-dir <path>       ONX config directory (default: /etc/onx)
  --env-file-name <name>    env filename in config dir (default: onx.env)
  --ref <branch|tag|sha>    git ref to pull (default: dev)
  --venv-dir-name <name>    venv directory under install dir (default: .venv-onx)
  -h, --help                Show help
EOF
}

fail() {
  echo "$*" >&2
  exit 1
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

ENV_FILE_PATH="${CONFIG_DIR}/${ENV_FILE_NAME}"
VENV_DIR="${INSTALL_DIR}/${VENV_DIR_NAME}"

[[ -d "${INSTALL_DIR}/.git" ]] || fail "Install dir is not a git repo: ${INSTALL_DIR}"
[[ -f "${INSTALL_DIR}/requirements-onx.txt" ]] || fail "requirements-onx.txt not found in ${INSTALL_DIR}"
[[ -f "${ENV_FILE_PATH}" ]] || fail "ONX env file not found: ${ENV_FILE_PATH}"
[[ -x "${VENV_DIR}/bin/python3" ]] || fail "ONX venv python not found: ${VENV_DIR}/bin/python3"

echo "[1/5] Pulling source..."
git -C "${INSTALL_DIR}" fetch --all --tags --prune
if git -C "${INSTALL_DIR}" rev-parse --verify --quiet "origin/${GIT_REF}" >/dev/null; then
  git -C "${INSTALL_DIR}" checkout -B "${GIT_REF}" "origin/${GIT_REF}"
else
  git -C "${INSTALL_DIR}" checkout "${GIT_REF}"
fi
git -C "${INSTALL_DIR}" pull --ff-only origin "${GIT_REF}" || true

echo "[2/5] Updating Python dependencies..."
"${VENV_DIR}/bin/python3" -m pip install --upgrade pip wheel setuptools
"${VENV_DIR}/bin/python3" -m pip install -r "${INSTALL_DIR}/requirements-onx.txt"

echo "[3/5] Applying migrations..."
(
  cd "${INSTALL_DIR}"
  set -a
  source "${ENV_FILE_PATH}"
  set +a
  "${VENV_DIR}/bin/python3" -m alembic -c alembic.ini upgrade head
)

echo "[4/5] Restarting service..."
systemctl daemon-reload
systemctl restart "${SERVICE_NAME}.service"

echo "[5/5] Done."
echo "Status: systemctl status ${SERVICE_NAME}.service --no-pager"
echo "Logs:   journalctl -u ${SERVICE_NAME}.service -f"
