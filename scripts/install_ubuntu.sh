#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Autixx/WGD_AWG_fix_multihop.git}"
GIT_REF="${GIT_REF:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/wgd-awg-multihop}"
CONFIG_DIR="${CONFIG_DIR:-/etc/wgdashboard}"
SERVICE_NAME="${SERVICE_NAME:-wg-dashboard}"
AUTO_INSTALL_AWG="${AUTO_INSTALL_AWG:-true}"
AWG_TOOLS_REPO="${AWG_TOOLS_REPO:-https://github.com/amnezia-vpn/amneziawg-tools.git}"
AWG_TOOLS_REF="${AWG_TOOLS_REF:-master}"
AWG_GO_REPO="${AWG_GO_REPO:-https://github.com/amnezia-vpn/amneziawg-go.git}"
AWG_GO_REF="${AWG_GO_REF:-master}"
BOOTSTRAP_INBOUND="${BOOTSTRAP_INBOUND:-}"
BOOTSTRAP_PROTOCOL="${BOOTSTRAP_PROTOCOL:-wg}"
BOOTSTRAP_ADDRESS="${BOOTSTRAP_ADDRESS:-10.66.66.1/24}"
BOOTSTRAP_LISTEN_PORT="${BOOTSTRAP_LISTEN_PORT:-51820}"
BOOTSTRAP_OUT_IF="${BOOTSTRAP_OUT_IF:-}"
BOOTSTRAP_DNS="${BOOTSTRAP_DNS:-1.1.1.1,1.0.0.1}"
BOOTSTRAP_FORCE="${BOOTSTRAP_FORCE:-false}"
BOOTSTRAP_START="${BOOTSTRAP_START:-true}"
AWG_JC="${AWG_JC:-}"
AWG_JMIN="${AWG_JMIN:-}"
AWG_JMAX="${AWG_JMAX:-}"
AWG_S1="${AWG_S1:-}"
AWG_S2="${AWG_S2:-}"
AWG_S3="${AWG_S3:-}"
AWG_S4="${AWG_S4:-}"
AWG_H1="${AWG_H1:-}"
AWG_H2="${AWG_H2:-}"
AWG_H3="${AWG_H3:-}"
AWG_H4="${AWG_H4:-}"

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/install_ubuntu.sh [options]

Options:
  --repo-url <url>        Git repository URL
  --ref <branch|tag|sha>  Git ref to checkout (default: main)
  --install-dir <path>    Project install directory (default: /opt/wgd-awg-multihop)
  --config-dir <path>     Runtime config dir (default: /etc/wgdashboard)
  --service-name <name>   systemd unit name without suffix (default: wg-dashboard)
  --no-install-awg        Do not auto-install amneziawg-tools/amneziawg-go
  --awg-tools-repo <url>  amneziawg-tools repository URL
  --awg-tools-ref <ref>   amneziawg-tools git ref (default: master)
  --awg-go-repo <url>     amneziawg-go repository URL
  --awg-go-ref <ref>      amneziawg-go git ref (default: master)
  --bootstrap-inbound <name>
                           Create inbound interface config (example: wg0 / awg0)
  --bootstrap-protocol <wg|awg>
                           Protocol for bootstrap inbound (default: wg)
  --bootstrap-address <cidr>
                           Interface address/CIDR (default: 10.66.66.1/24)
  --bootstrap-listen-port <port>
                           Listen port for inbound (default: 51820)
  --bootstrap-out-if <iface>
                           Outbound NIC for NAT; auto-detected by default route
  --bootstrap-dns <dns1,dns2>
                           DNS pushed to peers by default template
  --bootstrap-force        Overwrite existing inbound config if it already exists
  --no-bootstrap-start     Create config but do not bring interface up
  --awg-jc <num>           AWG2.0 Jc value (default: random)
  --awg-jmin <num>         AWG2.0 Jmin value (default: random)
  --awg-jmax <num>         AWG2.0 Jmax value (default: random)
  --awg-s1 <num>           AWG2.0 S1 value (default: random)
  --awg-s2 <num>           AWG2.0 S2 value (default: random)
  --awg-s3 <num>           AWG2.0 S3 value (default: random)
  --awg-s4 <num>           AWG2.0 S4 value (default: random)
  --awg-h1 <num>           AWG2.0 H1 value (default: random)
  --awg-h2 <num>           AWG2.0 H2 value (default: random)
  --awg-h3 <num>           AWG2.0 H3 value (default: random)
  --awg-h4 <num>           AWG2.0 H4 value (default: random)
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
  ((value >= 1 && value <= 65535))
}

validate_int() {
  local value="$1"
  [[ "${value}" =~ ^-?[0-9]+$ ]]
}

version_ge() {
  local left="$1"
  local right="$2"
  python3 - "$left" "$right" <<'PY'
import re, sys

def parse(v: str):
    parts = [int(x) for x in re.findall(r'\d+', v)]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

print(0 if parse(sys.argv[1]) >= parse(sys.argv[2]) else 1)
PY
}

ensure_go_toolchain() {
  local min_version="$1"
  local current_version=""
  local arch go_arch download_version download_url tarball

  if command -v go >/dev/null 2>&1; then
    current_version="$(go version | awk '{print $3}' | sed 's/^go//')"
    if [[ "$(version_ge "${current_version}" "${min_version}")" == "0" ]]; then
      echo "[awg] Go toolchain is compatible (${current_version})."
      return
    fi
  fi

  case "$(uname -m)" in
    x86_64|amd64)
      go_arch="amd64"
      ;;
    aarch64|arm64)
      go_arch="arm64"
      ;;
    *)
      fail "[awg] Unsupported CPU architecture for auto Go install: $(uname -m)"
      ;;
  esac

  download_version="$(python3 - "${min_version}" "${go_arch}" <<'PY'
import json, re, sys, urllib.request

min_version = sys.argv[1]
arch = sys.argv[2]
major_minor = ".".join(min_version.split(".")[:2])

def as_tuple(v: str):
    nums = [int(x) for x in re.findall(r"\d+", v)]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])

with urllib.request.urlopen("https://go.dev/dl/?mode=json&include=all", timeout=30) as r:
    releases = json.loads(r.read().decode("utf-8"))

candidates = []
for rel in releases:
    tag = rel.get("version", "")
    if not tag.startswith("go"):
        continue
    v = tag[2:]
    if not v.startswith(major_minor + "."):
        continue
    for f in rel.get("files", []):
        if f.get("os") == "linux" and f.get("arch") == arch and f.get("kind") == "archive" and f.get("filename", "").endswith(".tar.gz"):
            candidates.append(v)
            break

if not candidates:
    print("")
else:
    candidates.sort(key=as_tuple, reverse=True)
    print(candidates[0])
PY
)"

  if [[ -z "${download_version}" ]]; then
    fail "[awg] Could not resolve Go download version for required ${min_version}."
  fi

  download_url="https://go.dev/dl/go${download_version}.linux-${go_arch}.tar.gz"
  tarball="/tmp/go${download_version}.linux-${go_arch}.tar.gz"

  echo "[awg] Installing Go ${download_version} from ${download_url}"
  curl -fsSL "${download_url}" -o "${tarball}"
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "${tarball}"
  rm -f "${tarball}"
  ln -sf /usr/local/go/bin/go /usr/local/bin/go
  ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt
  export PATH="/usr/local/go/bin:/usr/local/bin:${PATH}"

  current_version="$(go version | awk '{print $3}' | sed 's/^go//')"
  if [[ "$(version_ge "${current_version}" "${min_version}")" != "0" ]]; then
    fail "[awg] Go install failed. Current version ${current_version}, required ${min_version}."
  fi
}

sync_git_checkout() {
  local repo_url="$1"
  local git_ref="$2"
  local target_dir="$3"

  if [[ -d "${target_dir}/.git" ]]; then
    git -C "${target_dir}" fetch --all --tags --prune
  else
    git clone "${repo_url}" "${target_dir}"
  fi

  if git -C "${target_dir}" rev-parse --verify --quiet "origin/${git_ref}" >/dev/null; then
    git -C "${target_dir}" checkout -B "${git_ref}" "origin/${git_ref}"
  else
    git -C "${target_dir}" checkout "${git_ref}"
  fi
}

install_awg_stack() {
  local tools_missing="false"
  local go_missing="false"
  local build_root tools_dir go_dir make_jobs required_go

  if ! command -v awg >/dev/null 2>&1 || ! command -v awg-quick >/dev/null 2>&1; then
    tools_missing="true"
  fi
  if ! command -v amneziawg-go >/dev/null 2>&1; then
    go_missing="true"
  fi

  if [[ "${tools_missing}" == "false" && "${go_missing}" == "false" ]]; then
    echo "[awg] awg, awg-quick and amneziawg-go are already installed."
    return
  fi

  echo "[awg] Installing missing AWG components from source..."

  make_jobs="$(nproc 2>/dev/null || echo 1)"
  build_root="$(mktemp -d /tmp/wgd-awg-build.XXXXXX)"
  tools_dir="${build_root}/amneziawg-tools"
  go_dir="${build_root}/amneziawg-go"

  if [[ "${tools_missing}" == "true" ]]; then
    echo "[awg] Building amneziawg-tools (${AWG_TOOLS_REF})..."
    sync_git_checkout "${AWG_TOOLS_REPO}" "${AWG_TOOLS_REF}" "${tools_dir}"
    make -C "${tools_dir}/src" -j"${make_jobs}" install WITH_WGQUICK=yes WITH_SYSTEMDUNITS=yes
  fi

  if [[ "${go_missing}" == "true" ]]; then
    echo "[awg] Building amneziawg-go (${AWG_GO_REF})..."
    sync_git_checkout "${AWG_GO_REPO}" "${AWG_GO_REF}" "${go_dir}"
    # Some amneziawg-go revisions publish `go x.y.z` which breaks `go mod` parsing.
    if [[ -f "${go_dir}/go.mod" ]]; then
      sed -E -i 's/^go ([0-9]+\.[0-9]+)\.[0-9]+$/go \1/' "${go_dir}/go.mod"
    fi
    required_go="$(awk '/^go /{print $2; exit}' "${go_dir}/go.mod")"
    [[ -z "${required_go}" ]] && required_go="1.24"
    ensure_go_toolchain "${required_go}"
    (
      cd "${go_dir}"
      GOTOOLCHAIN=auto go mod tidy
    )
    make -C "${go_dir}" -j"${make_jobs}" install
  fi

  rm -rf "${build_root}"

  command -v awg >/dev/null 2>&1 || fail "[awg] Install failed: awg not found in PATH."
  command -v awg-quick >/dev/null 2>&1 || fail "[awg] Install failed: awg-quick not found in PATH."
  command -v amneziawg-go >/dev/null 2>&1 || fail "[awg] Install failed: amneziawg-go not found in PATH."
}

create_bootstrap_inbound() {
  local interface_name="$1"
  local protocol="$2"
  local address_cidr="$3"
  local listen_port="$4"
  local out_if="$5"
  local dns_value="$6"
  local force="$7"
  local should_start="$8"
  local conf_dir conf_path quick_bin nat_subnet private_key public_key service_unit
  local awg_jc="$9"
  local awg_jmin="${10}"
  local awg_jmax="${11}"
  local awg_s1="${12}"
  local awg_s2="${13}"
  local awg_s3="${14}"
  local awg_s4="${15}"
  local awg_h1="${16}"
  local awg_h2="${17}"
  local awg_h3="${18}"
  local awg_h4="${19}"

  [[ "${interface_name}" =~ ^[a-zA-Z0-9_.-]{1,15}$ ]] || fail "[bootstrap] Invalid interface name: ${interface_name}"
  [[ "${protocol}" == "wg" || "${protocol}" == "awg" ]] || fail "[bootstrap] Protocol must be wg or awg."
  validate_port "${listen_port}" || fail "[bootstrap] Invalid port: ${listen_port}"

  if [[ "${protocol}" == "awg" ]]; then
    local generated
    generated="$(python3 - <<'PY'
import random
jmin = random.randint(20, 200)
jmax = random.randint(jmin + 50, jmin + 1200)
hashes = random.sample(range(1, (2 ** 31) - 1), 4)
print(
    random.randint(3, 15),
    jmin,
    jmax,
    random.randint(0, 255),
    random.randint(0, 255),
    random.randint(0, 255),
    random.randint(0, 255),
    hashes[0], hashes[1], hashes[2], hashes[3]
)
PY
)"
    local g_jc g_jmin g_jmax g_s1 g_s2 g_s3 g_s4 g_h1 g_h2 g_h3 g_h4
    read -r g_jc g_jmin g_jmax g_s1 g_s2 g_s3 g_s4 g_h1 g_h2 g_h3 g_h4 <<< "${generated}"

    [[ -z "${awg_jc}" ]] && awg_jc="${g_jc}"
    [[ -z "${awg_jmin}" ]] && awg_jmin="${g_jmin}"
    [[ -z "${awg_jmax}" ]] && awg_jmax="${g_jmax}"
    [[ -z "${awg_s1}" ]] && awg_s1="${g_s1}"
    [[ -z "${awg_s2}" ]] && awg_s2="${g_s2}"
    [[ -z "${awg_s3}" ]] && awg_s3="${g_s3}"
    [[ -z "${awg_s4}" ]] && awg_s4="${g_s4}"
    [[ -z "${awg_h1}" ]] && awg_h1="${g_h1}"
    [[ -z "${awg_h2}" ]] && awg_h2="${g_h2}"
    [[ -z "${awg_h3}" ]] && awg_h3="${g_h3}"
    [[ -z "${awg_h4}" ]] && awg_h4="${g_h4}"

    for numeric in "${awg_jc}" "${awg_jmin}" "${awg_jmax}" "${awg_s1}" "${awg_s2}" "${awg_s3}" "${awg_s4}" "${awg_h1}" "${awg_h2}" "${awg_h3}" "${awg_h4}"; do
      validate_int "${numeric}" || fail "[bootstrap] AWG parameters must be integer values."
    done
    ((awg_jmax > awg_jmin)) || fail "[bootstrap] AWG Jmax must be greater than Jmin."
  fi

  quick_bin="${protocol}-quick"
  command -v "${quick_bin}" >/dev/null 2>&1 || fail "[bootstrap] ${quick_bin} is not installed."
  if [[ "${protocol}" == "awg" ]]; then
    command -v amneziawg-go >/dev/null 2>&1 || fail "[bootstrap] amneziawg-go is not installed."
  fi
  command -v wg >/dev/null 2>&1 || fail "[bootstrap] wg binary is required for key generation."

  if [[ "${protocol}" == "wg" ]]; then
    conf_dir="/etc/wireguard"
  else
    conf_dir="/etc/amnezia/amneziawg"
  fi
  mkdir -p "${conf_dir}"
  conf_path="${conf_dir}/${interface_name}.conf"

  if [[ -z "${out_if}" ]]; then
    out_if="$(ip -o -4 route show to default | awk '{print $5}' | head -n 1)"
  fi
  [[ -n "${out_if}" ]] || fail "[bootstrap] Failed to detect outbound NIC. Use --bootstrap-out-if."

  nat_subnet="$(python3 - <<PY
import ipaddress
print(ipaddress.ip_interface("${address_cidr}").network)
PY
)"

  private_key="$(wg genkey)"
  public_key="$(printf '%s' "${private_key}" | wg pubkey)"

  if [[ -f "${conf_path}" && "${force}" != "true" ]]; then
    fail "[bootstrap] ${conf_path} already exists. Use --bootstrap-force to overwrite."
  fi

  umask 077
  cat > "${conf_path}" <<EOF
[Interface]
PrivateKey = ${private_key}
Address = ${address_cidr}
ListenPort = ${listen_port}
DNS = ${dns_value}
PostUp = iptables -t nat -A POSTROUTING -s ${nat_subnet} -o ${out_if} -j MASQUERADE; iptables -A FORWARD -i ${interface_name} -j ACCEPT; iptables -A FORWARD -o ${interface_name} -j ACCEPT
PreDown = iptables -t nat -D POSTROUTING -s ${nat_subnet} -o ${out_if} -j MASQUERADE; iptables -D FORWARD -i ${interface_name} -j ACCEPT; iptables -D FORWARD -o ${interface_name} -j ACCEPT
SaveConfig = false
EOF
  if [[ "${protocol}" == "awg" ]]; then
    cat >> "${conf_path}" <<EOF
Jc = ${awg_jc}
Jmin = ${awg_jmin}
Jmax = ${awg_jmax}
S1 = ${awg_s1}
S2 = ${awg_s2}
S3 = ${awg_s3}
S4 = ${awg_s4}
H1 = ${awg_h1}
H2 = ${awg_h2}
H3 = ${awg_h3}
H4 = ${awg_h4}
EOF
  fi
  chmod 600 "${conf_path}"

  cat > /etc/sysctl.d/99-wgd-forward.conf <<'EOF'
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
EOF
  sysctl -p /etc/sysctl.d/99-wgd-forward.conf >/dev/null

  if [[ "${should_start}" == "true" ]]; then
    "${quick_bin}" down "${conf_path}" >/dev/null 2>&1 || true
    "${quick_bin}" up "${conf_path}"
    service_unit="${quick_bin}@${interface_name}.service"
    if systemctl list-unit-files --type=service | awk '{print $1}' | grep -qx "${service_unit}"; then
      systemctl enable "${service_unit}" >/dev/null 2>&1 || true
    fi
  fi

  echo
  echo "[bootstrap] Inbound interface created:"
  echo "  Name:       ${interface_name}"
  echo "  Protocol:   ${protocol}"
  echo "  Config:     ${conf_path}"
  echo "  ListenPort: ${listen_port}"
  echo "  Address:    ${address_cidr}"
  echo "  NAT via:    ${out_if}"
  echo "  PublicKey:  ${public_key}"
  if [[ "${protocol}" == "awg" ]]; then
    echo "  AWG2.0:     Jc=${awg_jc} Jmin=${awg_jmin} Jmax=${awg_jmax} S1=${awg_s1} S2=${awg_s2} S3=${awg_s3} S4=${awg_s4} H1=${awg_h1} H2=${awg_h2} H3=${awg_h3} H4=${awg_h4}"
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
    --config-dir)
      CONFIG_DIR="$2"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --no-install-awg)
      AUTO_INSTALL_AWG="false"
      shift 1
      ;;
    --awg-tools-repo)
      AWG_TOOLS_REPO="$2"
      shift 2
      ;;
    --awg-tools-ref)
      AWG_TOOLS_REF="$2"
      shift 2
      ;;
    --awg-go-repo)
      AWG_GO_REPO="$2"
      shift 2
      ;;
    --awg-go-ref)
      AWG_GO_REF="$2"
      shift 2
      ;;
    --bootstrap-inbound)
      BOOTSTRAP_INBOUND="$2"
      shift 2
      ;;
    --bootstrap-protocol)
      BOOTSTRAP_PROTOCOL="$2"
      shift 2
      ;;
    --bootstrap-address)
      BOOTSTRAP_ADDRESS="$2"
      shift 2
      ;;
    --bootstrap-listen-port)
      BOOTSTRAP_LISTEN_PORT="$2"
      shift 2
      ;;
    --bootstrap-out-if)
      BOOTSTRAP_OUT_IF="$2"
      shift 2
      ;;
    --bootstrap-dns)
      BOOTSTRAP_DNS="$2"
      shift 2
      ;;
    --bootstrap-force)
      BOOTSTRAP_FORCE="true"
      shift 1
      ;;
    --no-bootstrap-start)
      BOOTSTRAP_START="false"
      shift 1
      ;;
    --awg-jc)
      AWG_JC="$2"
      shift 2
      ;;
    --awg-jmin)
      AWG_JMIN="$2"
      shift 2
      ;;
    --awg-jmax)
      AWG_JMAX="$2"
      shift 2
      ;;
    --awg-s1)
      AWG_S1="$2"
      shift 2
      ;;
    --awg-s2)
      AWG_S2="$2"
      shift 2
      ;;
    --awg-s3)
      AWG_S3="$2"
      shift 2
      ;;
    --awg-s4)
      AWG_S4="$2"
      shift 2
      ;;
    --awg-h1)
      AWG_H1="$2"
      shift 2
      ;;
    --awg-h2)
      AWG_H2="$2"
      shift 2
      ;;
    --awg-h3)
      AWG_H3="$2"
      shift 2
      ;;
    --awg-h4)
      AWG_H4="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu/Debian apt-based systems only."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[1/9] Installing OS dependencies..."
apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  git \
  iproute2 \
  iptables \
  net-tools \
  python3 \
  python3-dev \
  python3-pip \
  python3-venv \
  build-essential \
  libffi-dev \
  libssl-dev

if ! command -v wg >/dev/null 2>&1 || ! command -v wg-quick >/dev/null 2>&1; then
  apt-get install -y wireguard wireguard-tools || apt-get install -y wireguard-tools
fi

mkdir -p /etc/wireguard

echo "[2/9] Ensuring AmneziaWG binaries..."
if [[ "${AUTO_INSTALL_AWG}" == "true" ]]; then
  install_awg_stack
else
  if ! command -v awg >/dev/null 2>&1 || ! command -v awg-quick >/dev/null 2>&1 || ! command -v amneziawg-go >/dev/null 2>&1; then
    echo "[WARN] AWG auto-install disabled and awg stack is incomplete (need awg, awg-quick, amneziawg-go)."
  fi
fi

echo "[3/9] Fetching project source..."
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" fetch --all --tags
else
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

if git -C "${INSTALL_DIR}" rev-parse --verify --quiet "origin/${GIT_REF}" >/dev/null; then
  git -C "${INSTALL_DIR}" checkout -B "${GIT_REF}" "origin/${GIT_REF}"
else
  git -C "${INSTALL_DIR}" checkout "${GIT_REF}"
fi

SRC_DIR="${INSTALL_DIR}/src"
if [[ ! -f "${SRC_DIR}/dashboard.py" ]]; then
  echo "Invalid source layout: ${SRC_DIR}/dashboard.py not found."
  exit 1
fi

echo "[4/9] Preparing runtime directories..."
mkdir -p "${SRC_DIR}/log" "${SRC_DIR}/download"
mkdir -p "${CONFIG_DIR}/db" "${CONFIG_DIR}/letsencrypt/work-dir" "${CONFIG_DIR}/letsencrypt/config-dir"

if [[ ! -f "${SRC_DIR}/ssl-tls.ini" ]]; then
  cat > "${SRC_DIR}/ssl-tls.ini" <<'EOF'
[SSL/TLS]
certificate_path =
private_key_path =
EOF
fi

echo "[5/9] Creating Python virtualenv..."
python3 -m venv "${SRC_DIR}/venv"

echo "[6/9] Installing Python dependencies..."
"${SRC_DIR}/venv/bin/python3" -m pip install --upgrade pip wheel setuptools
"${SRC_DIR}/venv/bin/python3" -m pip install -r "${SRC_DIR}/requirements.txt"

chmod +x "${SRC_DIR}/wgd.sh"

echo "[7/9] Installing systemd service..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=WGDashboard (AWG Multi-hop Fork)
After=network-online.target
Wants=network-online.target
ConditionPathIsDirectory=/etc/wireguard

[Service]
Type=forking
Environment=CONFIGURATION_PATH=${CONFIG_DIR}
WorkingDirectory=${SRC_DIR}
PIDFile=${SRC_DIR}/gunicorn.pid
ExecStart=${SRC_DIR}/wgd.sh start
ExecStop=${SRC_DIR}/wgd.sh stop
ExecReload=${SRC_DIR}/wgd.sh restart
TimeoutSec=120
Restart=always
RestartSec=5
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

echo "[8/9] Enabling and starting service..."
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo "[9/9] Optional inbound bootstrap..."
if [[ -n "${BOOTSTRAP_INBOUND}" ]]; then
  create_bootstrap_inbound \
    "${BOOTSTRAP_INBOUND}" \
    "${BOOTSTRAP_PROTOCOL}" \
    "${BOOTSTRAP_ADDRESS}" \
    "${BOOTSTRAP_LISTEN_PORT}" \
    "${BOOTSTRAP_OUT_IF}" \
    "${BOOTSTRAP_DNS}" \
    "${BOOTSTRAP_FORCE}" \
    "${BOOTSTRAP_START}" \
    "${AWG_JC}" \
    "${AWG_JMIN}" \
    "${AWG_JMAX}" \
    "${AWG_S1}" \
    "${AWG_S2}" \
    "${AWG_S3}" \
    "${AWG_S4}" \
    "${AWG_H1}" \
    "${AWG_H2}" \
    "${AWG_H3}" \
    "${AWG_H4}"
else
  echo "[bootstrap] skipped (use --bootstrap-inbound <name> to enable)"
fi

echo
echo "Installation complete."
echo "Service: ${SERVICE_NAME}.service"
echo "Status:  systemctl status ${SERVICE_NAME}.service --no-pager"
echo "Logs:    journalctl -u ${SERVICE_NAME}.service -f"
echo "Config:  ${CONFIG_DIR}/wg-dashboard.ini"
echo "URL:     http://<server-ip>:10086"
