from __future__ import annotations

from textwrap import dedent

from onx.core.config import get_settings
from onx.db.models.node import Node
from onx.deploy.ssh_executor import SSHExecutor


RUNNER_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    ACTION="${1:-}"
    IFACE="${2:-}"
    CONF_DIR="${ONX_LINK_CONF_DIR:-__ONX_CONF_DIR__}"
    CONF_PATH="${CONF_DIR}/${IFACE}.conf"
    QUICK_BIN=""
    SHOW_BIN=""

    select_driver() {
      if [[ ! -f "${CONF_PATH}" ]]; then
        echo "missing interface config: ${CONF_PATH}" >&2
        exit 1
      fi
      if grep -Eiq '^[[:space:]]*(Jc|Jmin|Jmax|S1|S2|S3|S4|H1|H2|H3|H4)[[:space:]]*=' "${CONF_PATH}"; then
        QUICK_BIN="awg-quick"
        SHOW_BIN="awg"
      else
        QUICK_BIN="wg-quick"
        SHOW_BIN="wg"
      fi
      command -v "${QUICK_BIN}" >/dev/null 2>&1 || {
        echo "missing runtime binary: ${QUICK_BIN}" >&2
        exit 1
      }
      command -v "${SHOW_BIN}" >/dev/null 2>&1 || {
        echo "missing runtime binary: ${SHOW_BIN}" >&2
        exit 1
      }
    }

    if [[ -z "${ACTION}" || -z "${IFACE}" ]]; then
      echo "usage: onx-link-runner <up|down|reload|status> <iface>" >&2
      exit 2
    fi

    select_driver

    case "${ACTION}" in
      up)
        "${QUICK_BIN}" down "${IFACE}" >/dev/null 2>&1 || true
        "${QUICK_BIN}" up "${CONF_PATH}"
        ;;
      down)
        "${QUICK_BIN}" down "${IFACE}" >/dev/null 2>&1 || true
        ;;
      reload)
        "${QUICK_BIN}" down "${IFACE}" >/dev/null 2>&1 || true
        "${QUICK_BIN}" up "${CONF_PATH}"
        ;;
      status)
        "${SHOW_BIN}" show "${IFACE}"
        ;;
      *)
        echo "unsupported action: ${ACTION}" >&2
        exit 2
        ;;
    esac
    """
)

UNIT_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX managed WG/AWG interface %i
    After=network-online.target
    Wants=network-online.target
    ConditionPathExists=__ONX_CONF_DIR__/%i.conf

    [Service]
    Type=oneshot
    RemainAfterExit=yes
    ExecStart=__ONX_RUNNER_PATH__ up %i
    ExecStop=__ONX_RUNNER_PATH__ down %i
    ExecReload=__ONX_RUNNER_PATH__ reload %i
    TimeoutStartSec=60
    TimeoutStopSec=30

    [Install]
    WantedBy=multi-user.target
    """
)

XRAY_UNIT_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX managed Xray service %i
    After=network-online.target
    Wants=network-online.target
    ConditionPathExists=__ONX_XRAY_CONF_DIR__/%i.json

    [Service]
    Type=simple
    ExecStart=/usr/local/bin/xray run -config __ONX_XRAY_CONF_DIR__/%i.json
    Restart=on-failure
    RestartSec=3
    AmbientCapabilities=CAP_NET_BIND_SERVICE
    NoNewPrivileges=true

    [Install]
    WantedBy=multi-user.target
    """
)

OPENVPN_UNIT_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX managed OpenVPN service %i
    After=network-online.target
    Wants=network-online.target
    ConditionPathExists=__ONX_OPENVPN_CLOAK_CONF_DIR__/%i-server.conf

    [Service]
    Type=simple
    ExecStart=/usr/sbin/openvpn --config __ONX_OPENVPN_CLOAK_CONF_DIR__/%i-server.conf
    Restart=on-failure
    RestartSec=3

    [Install]
    WantedBy=multi-user.target
    """
)

CLOAK_UNIT_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX managed Cloak service %i
    After=network-online.target onx-openvpn@%i.service
    Wants=network-online.target
    Requires=onx-openvpn@%i.service
    ConditionPathExists=__ONX_OPENVPN_CLOAK_CONF_DIR__/%i-cloak.json

    [Service]
    Type=simple
    ExecStart=/usr/local/bin/ck-server -c __ONX_OPENVPN_CLOAK_CONF_DIR__/%i-cloak.json
    Restart=on-failure
    RestartSec=3

    [Install]
    WantedBy=multi-user.target
    """
)

TRANSIT_RUNNER_SCRIPT = dedent(
    """\
    #!/usr/bin/env python3
    import json
    import shutil
    import subprocess
    import sys

    CONF_DIR = "__ONX_TRANSIT_CONF_DIR__"

    def fail(message: str) -> None:
        print(message, file=sys.stderr)
        raise SystemExit(1)

    def ensure_binary(name: str) -> str:
        path = shutil.which(name)
        if not path:
            fail(f"missing runtime binary: {name}")
        return path

    def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        if check and result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            fail(stderr or f"command failed: {' '.join(cmd)}")
        return result

    def iptables(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run([IPTABLES_BIN, "-w", "-t", "mangle", *args], check=check)

    def rule_exists(chain: str, rule: list[str]) -> bool:
        return iptables("-C", chain, *rule, check=False).returncode == 0

    def ensure_rule(chain: str, rule: list[str]) -> None:
        if not rule_exists(chain, rule):
            iptables("-A", chain, *rule)

    def ensure_prerouting_jump(interface_name: str, chain_name: str) -> None:
        rule = ["-i", interface_name, "-j", chain_name]
        if not rule_exists("PREROUTING", rule):
            iptables("-A", "PREROUTING", *rule)

    def remove_prerouting_jump(interface_name: str, chain_name: str) -> None:
        rule = ["-i", interface_name, "-j", chain_name]
        while rule_exists("PREROUTING", rule):
            iptables("-D", "PREROUTING", *rule, check=False)

    def clear_chain(chain_name: str) -> None:
        if iptables("-S", chain_name, check=False).returncode != 0:
            iptables("-N", chain_name, check=False)
            return
        iptables("-F", chain_name, check=False)

    def drop_chain(chain_name: str) -> None:
        iptables("-F", chain_name, check=False)
        iptables("-X", chain_name, check=False)

    def remove_ip_rule(mark: int, table_id: int, priority: int) -> None:
        while True:
            result = run(
                [IP_BIN, "rule", "del", "fwmark", str(mark), "table", str(table_id), "priority", str(priority)],
                check=False,
            )
            if result.returncode != 0:
                break

    def remove_source_rule(source_ip: str, table_id: int, priority: int) -> None:
        while True:
            result = run(
                [IP_BIN, "rule", "del", "from", f"{source_ip}/32", "table", str(table_id), "priority", str(priority)],
                check=False,
            )
            if result.returncode != 0:
                break

    def apply(config: dict) -> None:
        chain_name = config["chain_name"]
        ingress_interface = config["ingress_interface"]
        transparent_port = int(config["transparent_port"])
        firewall_mark = int(config["firewall_mark"])
        route_table_id = int(config["route_table_id"])
        rule_priority = int(config["rule_priority"])
        next_hop = dict(config.get("next_hop_runtime_json") or {})
        capture_protocols = list(config.get("capture_protocols_json") or [])
        capture_cidrs = list(config.get("capture_cidrs_json") or [])
        excluded_cidrs = list(config.get("excluded_cidrs_json") or [])
        bypass_ipv4 = list(config.get("management_bypass_ipv4_json") or [])
        bypass_tcp_ports = [int(item) for item in (config.get("management_bypass_tcp_ports_json") or [])]

        clear_chain(chain_name)
        ensure_prerouting_jump(ingress_interface, chain_name)
        ensure_rule(chain_name, ["-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"])
        for port in bypass_tcp_ports:
            ensure_rule(
                chain_name,
                ["-m", "addrtype", "--dst-type", "LOCAL", "-p", "tcp", "--dport", str(port), "-j", "RETURN"],
            )
        for cidr in bypass_ipv4:
            ensure_rule(chain_name, ["-d", cidr, "-j", "RETURN"])
        for cidr in excluded_cidrs:
            ensure_rule(chain_name, ["-d", cidr, "-j", "RETURN"])
        for proto in capture_protocols:
            for cidr in capture_cidrs:
                ensure_rule(
                    chain_name,
                    [
                        "-p",
                        proto,
                        "-d",
                        cidr,
                        "-j",
                        "TPROXY",
                        "--on-port",
                        str(transparent_port),
                        "--tproxy-mark",
                        f"{firewall_mark}/{firewall_mark}",
                    ],
                )
        ensure_rule(chain_name, ["-j", "RETURN"])
        remove_ip_rule(firewall_mark, route_table_id, rule_priority)
        run([IP_BIN, "rule", "add", "fwmark", str(firewall_mark), "table", str(route_table_id), "priority", str(rule_priority)])
        run([IP_BIN, "route", "replace", "local", "0.0.0.0/0", "dev", "lo", "table", str(route_table_id)])
        if next_hop.get("attached"):
            source_ip = str(next_hop["source_ip"])
            egress_table_id = int(next_hop["egress_table_id"])
            egress_rule_priority = int(next_hop["egress_rule_priority"])
            interface_name = str(next_hop["interface_name"])
            remove_source_rule(source_ip, egress_table_id, egress_rule_priority)
            run(
                [
                    IP_BIN,
                    "rule",
                    "add",
                    "from",
                    f"{source_ip}/32",
                    "table",
                    str(egress_table_id),
                    "priority",
                    str(egress_rule_priority),
                ]
            )
            run([IP_BIN, "route", "replace", "default", "dev", interface_name, "table", str(egress_table_id)])

    def cleanup(config: dict) -> None:
        chain_name = config["chain_name"]
        ingress_interface = config["ingress_interface"]
        firewall_mark = int(config["firewall_mark"])
        route_table_id = int(config["route_table_id"])
        rule_priority = int(config["rule_priority"])
        next_hop = dict(config.get("next_hop_runtime_json") or {})
        remove_prerouting_jump(ingress_interface, chain_name)
        drop_chain(chain_name)
        remove_ip_rule(firewall_mark, route_table_id, rule_priority)
        run([IP_BIN, "route", "del", "local", "0.0.0.0/0", "dev", "lo", "table", str(route_table_id)], check=False)
        if next_hop.get("attached"):
            source_ip = str(next_hop["source_ip"])
            egress_table_id = int(next_hop["egress_table_id"])
            egress_rule_priority = int(next_hop["egress_rule_priority"])
            remove_source_rule(source_ip, egress_table_id, egress_rule_priority)
            run([IP_BIN, "route", "del", "default", "dev", str(next_hop["interface_name"]), "table", str(egress_table_id)], check=False)

    def status(config: dict) -> None:
        chain_name = config["chain_name"]
        if iptables("-S", chain_name, check=False).returncode != 0:
            fail(f"transit chain is absent: {chain_name}")
        print(json.dumps({"status": "present", "chain_name": chain_name}))

    if len(sys.argv) != 3:
        fail("usage: onx-transit-runner <up|down|reload|status> <policy-id>")

    IPTABLES_BIN = ensure_binary("iptables")
    IP_BIN = ensure_binary("ip")
    action = sys.argv[1]
    policy_id = sys.argv[2]
    conf_path = f"{CONF_DIR}/{policy_id}.json"
    try:
        with open(conf_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except FileNotFoundError:
        fail(f"missing transit config: {conf_path}")

    if action == "up":
        apply(config)
    elif action == "down":
        cleanup(config)
    elif action == "reload":
        cleanup(config)
        apply(config)
    elif action == "status":
        status(config)
    else:
        fail(f"unsupported action: {action}")
    """
)

TRANSIT_UNIT_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX managed transit policy %i
    After=network-online.target
    Wants=network-online.target
    ConditionPathExists=__ONX_TRANSIT_CONF_DIR__/%i.json

    [Service]
    Type=oneshot
    RemainAfterExit=yes
    ExecStart=__ONX_TRANSIT_RUNNER_PATH__ up %i
    ExecStop=__ONX_TRANSIT_RUNNER_PATH__ down %i
    ExecReload=__ONX_TRANSIT_RUNNER_PATH__ reload %i
    TimeoutStartSec=60
    TimeoutStopSec=30

    [Install]
    WantedBy=multi-user.target
    """
)

NODE_AGENT_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    ENV_FILE="${ONX_NODE_AGENT_ENV_FILE:-__ONX_AGENT_ENV_PATH__}"
    if [[ ! -f "${ENV_FILE}" ]]; then
      echo "[onx-node-agent] missing env file: ${ENV_FILE}" >&2
      exit 1
    fi
    # shellcheck disable=SC1090
    source "${ENV_FILE}"

    : "${ONX_NODE_ID:?missing ONX_NODE_ID}"
    : "${ONX_NODE_AGENT_TOKEN:?missing ONX_NODE_AGENT_TOKEN}"
    : "${ONX_NODE_AGENT_REPORT_URL:?missing ONX_NODE_AGENT_REPORT_URL}"

    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

    python3 - <<'PY'
    import json
    import os
    import socket
    import subprocess
    import sys
    import urllib.error
    import urllib.request
    from datetime import datetime, timezone

    report_url = os.environ["ONX_NODE_AGENT_REPORT_URL"]
    node_id = os.environ["ONX_NODE_ID"]
    token = os.environ["ONX_NODE_AGENT_TOKEN"]
    agent_version = os.environ.get("ONX_NODE_AGENT_VERSION", "")

    try:
        result = subprocess.run(
            ["awg", "show", "all", "dump"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        print("[onx-node-agent] awg not found", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(result.stderr.strip() or "[onx-node-agent] awg show all dump failed", file=sys.stderr)
        sys.exit(1)

    peers = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = line.split("\\t")
        if len(fields) < 9:
            continue
        iface, peer_public_key, _psk, endpoint, allowed_ips, latest_handshake, rx_bytes, tx_bytes, _keepalive = fields[:9]
        if not peer_public_key or peer_public_key == "(none)":
            continue
        try:
            hs = int(latest_handshake)
            handshake_at = datetime.fromtimestamp(hs, tz=timezone.utc).isoformat() if hs > 0 else None
        except ValueError:
            handshake_at = None
        try:
            rx_value = int(rx_bytes)
        except ValueError:
            rx_value = 0
        try:
            tx_value = int(tx_bytes)
        except ValueError:
            tx_value = 0

        peers.append(
            {
                "interface_name": iface,
                "peer_public_key": peer_public_key,
                "endpoint": None if endpoint in {"", "(none)"} else endpoint,
                "allowed_ips": [] if allowed_ips in {"", "(none)"} else [item for item in allowed_ips.split(",") if item],
                "rx_bytes": max(rx_value, 0),
                "tx_bytes": max(tx_value, 0),
                "latest_handshake_at": handshake_at,
                "metadata": {},
            }
        )

    payload = {
        "agent_version": agent_version or None,
        "hostname": socket.gethostname(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "peers": peers,
    }
    req = urllib.request.Request(
        report_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-ONX-Node-Id": node_id,
            "X-ONX-Node-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"unexpected HTTP status {resp.status}")
    except urllib.error.HTTPError as exc:
        print(f"[onx-node-agent] report failed: HTTP {exc.code}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[onx-node-agent] report failed: {exc}", file=sys.stderr)
        sys.exit(1)
    PY
    """
)

NODE_AGENT_SERVICE_TEMPLATE = dedent(
    """\
    [Unit]
    Description=ONX node agent peer traffic reporter
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=oneshot
    EnvironmentFile=-__ONX_AGENT_ENV_PATH__
    ExecStart=__ONX_AGENT_PATH__
    TimeoutStartSec=30
    """
)

NODE_AGENT_TIMER_TEMPLATE = dedent(
    """\
    [Unit]
    Description=Run ONX node agent periodically

    [Timer]
    OnBootSec=20s
    OnUnitActiveSec=__ONX_AGENT_INTERVAL__s
    Unit=onx-node-agent.service

    [Install]
    WantedBy=timers.target
    """
)

AWG_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    AWG_TOOLS_REPO="__AWG_TOOLS_REPO__"
    AWG_TOOLS_REF="__AWG_TOOLS_REF__"
    AWG_GO_REPO="__AWG_GO_REPO__"
    AWG_GO_REF="__AWG_GO_REF__"
    GO_BOOTSTRAP_VERSION="__GO_BOOTSTRAP_VERSION__"

    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/go/bin:/usr/local/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[awg] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
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

    install_go_if_needed() {
      if command -v go >/dev/null 2>&1; then
        return
      fi

      local arch tarball url
      arch="$(uname -m)"
      case "${arch}" in
        x86_64|amd64) arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
        *)
          fail "[awg] Unsupported CPU architecture for Go bootstrap: ${arch}"
          ;;
      esac

      tarball="/tmp/go${GO_BOOTSTRAP_VERSION}.linux-${arch}.tar.gz"
      url="https://go.dev/dl/go${GO_BOOTSTRAP_VERSION}.linux-${arch}.tar.gz"

      echo "[awg] Installing Go ${GO_BOOTSTRAP_VERSION} from ${url}"
      curl -fsSL "${url}" -o "${tarball}"
      ${SUDO} rm -rf /usr/local/go
      ${SUDO} tar -C /usr/local -xzf "${tarball}"
      rm -f "${tarball}"
      ${SUDO} ln -sf /usr/local/go/bin/go /usr/local/bin/go
      ${SUDO} ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt
    }

    install_awg_stack() {
      local tools_missing="false"
      local go_missing="false"
      local build_root tools_dir go_dir make_jobs

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

      ${SUDO} apt-get update
      ${SUDO} apt-get install -y \
        ca-certificates \
        curl \
        git \
        python3 \
        build-essential \
        make \
        gcc \
        libc6-dev \
        libmnl-dev \
        libelf-dev \
        pkg-config \
        iptables \
        ipset \
        resolvconf

      install_go_if_needed

      make_jobs="$(nproc 2>/dev/null || echo 1)"
      build_root="$(mktemp -d /tmp/onx-awg-build.XXXXXX)"
      tools_dir="${build_root}/amneziawg-tools"
      go_dir="${build_root}/amneziawg-go"

      if [[ "${tools_missing}" == "true" ]]; then
        echo "[awg] Building amneziawg-tools (${AWG_TOOLS_REF})..."
        sync_git_checkout "${AWG_TOOLS_REPO}" "${AWG_TOOLS_REF}" "${tools_dir}"
        ${SUDO} make -C "${tools_dir}/src" -j"${make_jobs}" install WITH_WGQUICK=yes WITH_SYSTEMDUNITS=yes
      fi

      if [[ "${go_missing}" == "true" ]]; then
        echo "[awg] Building amneziawg-go (${AWG_GO_REF})..."
        sync_git_checkout "${AWG_GO_REPO}" "${AWG_GO_REF}" "${go_dir}"
        if [[ -f "${go_dir}/go.mod" ]]; then
          sed -E -i 's/^go ([0-9]+\\.[0-9]+)\\.[0-9]+$/go \\1/' "${go_dir}/go.mod"
        fi
        (
          cd "${go_dir}"
          GOTOOLCHAIN=auto go mod tidy
        )
        ${SUDO} make -C "${go_dir}" -j"${make_jobs}" install
      fi

      rm -rf "${build_root}"

      command -v awg >/dev/null 2>&1 || fail "[awg] Install failed: awg not found."
      command -v awg-quick >/dev/null 2>&1 || fail "[awg] Install failed: awg-quick not found."
      command -v amneziawg-go >/dev/null 2>&1 || fail "[awg] Install failed: amneziawg-go not found."
      command -v iptables >/dev/null 2>&1 || fail "[awg] Install failed: iptables not found."
      command -v ipset >/dev/null 2>&1 || fail "[awg] Install failed: ipset not found."
      command -v systemctl >/dev/null 2>&1 || fail "[awg] Install failed: systemctl not found."
    }

    setup_privilege
    install_awg_stack
    """
)

WG_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[wg] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
    }

    install_wg_stack() {
      ${SUDO} apt-get update
      ${SUDO} apt-get install -y ca-certificates curl wireguard-tools iptables ipset resolvconf
      command -v wg >/dev/null 2>&1 || fail "[wg] Install failed: wg not found."
      command -v wg-quick >/dev/null 2>&1 || fail "[wg] Install failed: wg-quick not found."
      command -v systemctl >/dev/null 2>&1 || fail "[wg] Install failed: systemctl not found."
    }

    setup_privilege
    install_wg_stack
    """
)

OPENVPN_CLOAK_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    CLOAK_VERSION="__CLOAK_VERSION__"
    CLOAK_RELEASE_BASE_URL="__CLOAK_RELEASE_BASE_URL__"

    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[openvpn_cloak] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
    }

    detect_arch() {
      case "$(uname -m)" in
        x86_64|amd64) echo "amd64" ;;
        aarch64|arm64) echo "arm64" ;;
        *)
          fail "[openvpn_cloak] Unsupported CPU architecture: $(uname -m)"
          ;;
      esac
    }

    install_openvpn_cloak_stack() {
      local arch url tmp_file

      ${SUDO} apt-get update
      ${SUDO} apt-get install -y ca-certificates curl openvpn

      if command -v ck-server >/dev/null 2>&1; then
        echo "[openvpn_cloak] ck-server already installed."
      else
        arch="$(detect_arch)"
        url="${CLOAK_RELEASE_BASE_URL}/v${CLOAK_VERSION}/ck-server-linux-${arch}-v${CLOAK_VERSION}"
        tmp_file="/tmp/ck-server-${arch}-${CLOAK_VERSION}"
        echo "[openvpn_cloak] Downloading ${url}"
        curl -fsSL "${url}" -o "${tmp_file}"
        ${SUDO} install -m 0755 "${tmp_file}" /usr/local/bin/ck-server
        rm -f "${tmp_file}"
      fi

      command -v openvpn >/dev/null 2>&1 || fail "[openvpn_cloak] Install failed: openvpn not found."
      command -v ck-server >/dev/null 2>&1 || fail "[openvpn_cloak] Install failed: ck-server not found."
      command -v systemctl >/dev/null 2>&1 || fail "[openvpn_cloak] Install failed: systemctl not found."
    }

    setup_privilege
    install_openvpn_cloak_stack
    """
)

XRAY_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    XRAY_INSTALL_SCRIPT_URL="__XRAY_INSTALL_SCRIPT_URL__"

    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[xray] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
    }

    install_xray_stack() {
      ${SUDO} apt-get update
      ${SUDO} apt-get install -y ca-certificates curl bash

      if command -v xray >/dev/null 2>&1; then
        echo "[xray] xray already installed."
      else
        echo "[xray] Installing via ${XRAY_INSTALL_SCRIPT_URL}"
        bash -c "$(curl -fsSL "${XRAY_INSTALL_SCRIPT_URL}")" @ install --without-geodata -u root
      fi

      command -v xray >/dev/null 2>&1 || fail "[xray] Install failed: xray not found."
      command -v systemctl >/dev/null 2>&1 || fail "[xray] Install failed: systemctl not found."
    }

    setup_privilege
    install_xray_stack
    """
)

TRANSIT_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[transit] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
    }

    install_transit_stack() {
      ${SUDO} apt-get update
      ${SUDO} apt-get install -y iptables iproute2 python3
      command -v iptables >/dev/null 2>&1 || fail "[transit] Install failed: iptables not found."
      command -v ip >/dev/null 2>&1 || fail "[transit] Install failed: iproute2 not found."
      command -v python3 >/dev/null 2>&1 || fail "[transit] Install failed: python3 not found."
      command -v systemctl >/dev/null 2>&1 || fail "[transit] Install failed: systemctl not found."
    }

    setup_privilege
    install_transit_stack
    """
)

SECURITY_INSTALL_SCRIPT = dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    SSH_PORT="__ONX_NODE_SSH_PORT__"

    export DEBIAN_FRONTEND=noninteractive
    export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
    SUDO=""

    fail() {
      echo "$*" >&2
      exit 1
    }

    setup_privilege() {
      if [[ "$(id -u)" -eq 0 ]]; then
        return
      fi
      if ! command -v sudo >/dev/null 2>&1; then
        fail "[security] Remote package install requires root or passwordless sudo."
      fi
      SUDO="sudo"
    }

    install_security_stack() {
      ${SUDO} apt-get update
      ${SUDO} apt-get install -y ufw fail2ban

      command -v ufw >/dev/null 2>&1 || fail "[security] Install failed: ufw not found."
      command -v fail2ban-client >/dev/null 2>&1 || fail "[security] Install failed: fail2ban-client not found."
      command -v systemctl >/dev/null 2>&1 || fail "[security] Install failed: systemctl not found."

      ${SUDO} ufw allow "${SSH_PORT}/tcp" >/dev/null 2>&1 || true
      ${SUDO} ufw --force enable >/dev/null 2>&1 || true
      ${SUDO} systemctl enable --now fail2ban >/dev/null 2>&1 || fail "[security] Failed to enable fail2ban."
    }

    setup_privilege
    install_security_stack
    """
)


class InterfaceRuntimeService:
    def __init__(self, executor: SSHExecutor) -> None:
        self._executor = executor
        self._settings = get_settings()

    @property
    def settings(self):
        return self._settings

    def ensure_runtime(self, node: Node, management_secret: str) -> None:
        runner_content = RUNNER_SCRIPT.replace("__ONX_CONF_DIR__", self._settings.onx_conf_dir)
        unit_content = (
            UNIT_TEMPLATE
            .replace("__ONX_CONF_DIR__", self._settings.onx_conf_dir)
            .replace("__ONX_RUNNER_PATH__", self._settings.onx_link_runner_path)
        )
        self._executor.write_file(node, management_secret, self._settings.onx_link_runner_path, runner_content)
        self._executor.run(node, management_secret, f"sh -lc 'chmod 755 \"{self._settings.onx_link_runner_path}\"'")

        self._executor.write_file(node, management_secret, self._settings.onx_link_unit_path, unit_content)
        code, _, stderr = self._executor.run(node, management_secret, "sh -lc 'systemctl daemon-reload'")
        if code != 0:
            raise RuntimeError(stderr or f"Failed to reload systemd on node {node.name}")

    def ensure_xray_runtime(self, node: Node, management_secret: str) -> None:
        unit_content = XRAY_UNIT_TEMPLATE.replace("__ONX_XRAY_CONF_DIR__", self._settings.onx_xray_conf_dir)
        self._executor.write_file(node, management_secret, self._settings.onx_xray_unit_path, unit_content)
        code, _, stderr = self._executor.run(node, management_secret, "sh -lc 'systemctl daemon-reload'")
        if code != 0:
            raise RuntimeError(stderr or f"Failed to reload systemd for Xray runtime on node {node.name}")

    def ensure_openvpn_cloak_runtime(self, node: Node, management_secret: str) -> None:
        openvpn_unit = OPENVPN_UNIT_TEMPLATE.replace("__ONX_OPENVPN_CLOAK_CONF_DIR__", self._settings.onx_openvpn_cloak_conf_dir)
        cloak_unit = CLOAK_UNIT_TEMPLATE.replace("__ONX_OPENVPN_CLOAK_CONF_DIR__", self._settings.onx_openvpn_cloak_conf_dir)
        self._executor.write_file(node, management_secret, self._settings.onx_openvpn_unit_path, openvpn_unit)
        self._executor.write_file(node, management_secret, self._settings.onx_cloak_unit_path, cloak_unit)
        code, _, stderr = self._executor.run(node, management_secret, "sh -lc 'systemctl daemon-reload'")
        if code != 0:
            raise RuntimeError(stderr or f"Failed to reload systemd for OpenVPN+Cloak runtime on node {node.name}")

    def ensure_transit_runtime(self, node: Node, management_secret: str) -> None:
        runner_content = TRANSIT_RUNNER_SCRIPT.replace("__ONX_TRANSIT_CONF_DIR__", self._settings.onx_transit_conf_dir)
        unit_content = (
            TRANSIT_UNIT_TEMPLATE
            .replace("__ONX_TRANSIT_CONF_DIR__", self._settings.onx_transit_conf_dir)
            .replace("__ONX_TRANSIT_RUNNER_PATH__", self._settings.onx_transit_runner_path)
        )
        self._executor.write_file(node, management_secret, self._settings.onx_transit_runner_path, runner_content)
        self._executor.run(node, management_secret, f"sh -lc 'chmod 755 \"{self._settings.onx_transit_runner_path}\"'")
        self._executor.write_file(node, management_secret, self._settings.onx_transit_unit_path, unit_content)
        code, _, stderr = self._executor.run(node, management_secret, "sh -lc 'systemctl daemon-reload'")
        if code != 0:
            raise RuntimeError(stderr or f"Failed to reload systemd for transit runtime on node {node.name}")

    def ensure_node_agent(
        self,
        node: Node,
        management_secret: str,
        *,
        node_id: str,
        token: str,
        report_url: str,
    ) -> dict:
        agent_script = NODE_AGENT_SCRIPT.replace("__ONX_AGENT_ENV_PATH__", self._settings.onx_node_agent_env_path)
        agent_service = (
            NODE_AGENT_SERVICE_TEMPLATE
            .replace("__ONX_AGENT_ENV_PATH__", self._settings.onx_node_agent_env_path)
            .replace("__ONX_AGENT_PATH__", self._settings.onx_node_agent_path)
        )
        agent_timer = NODE_AGENT_TIMER_TEMPLATE.replace(
            "__ONX_AGENT_INTERVAL__", str(max(15, int(self._settings.onx_node_agent_interval_seconds)))
        )
        env_content = dedent(
            f"""\
            ONX_NODE_ID={node_id}
            ONX_NODE_AGENT_TOKEN={token}
            ONX_NODE_AGENT_REPORT_URL={report_url}
            ONX_NODE_AGENT_VERSION={self._settings.onx_node_agent_version}
            """
        )
        self._executor.run(
            node,
            management_secret,
            "sh -lc '"
            "systemctl stop onx-node-agent.timer >/dev/null 2>&1 || true; "
            "systemctl stop onx-node-agent.service >/dev/null 2>&1 || true; "
            "systemctl disable onx-node-agent.timer >/dev/null 2>&1 || true; "
            "systemctl reset-failed onx-node-agent.timer onx-node-agent.service >/dev/null 2>&1 || true"
            "'",
        )
        self._executor.write_file(node, management_secret, self._settings.onx_node_agent_path, agent_script)
        self._executor.run(node, management_secret, f"sh -lc 'chmod 755 \"{self._settings.onx_node_agent_path}\"'")
        self._executor.write_file(node, management_secret, self._settings.onx_node_agent_env_path, env_content)
        self._executor.run(node, management_secret, f"sh -lc 'chmod 600 \"{self._settings.onx_node_agent_env_path}\"'")
        self._executor.write_file(node, management_secret, self._settings.onx_node_agent_service_path, agent_service)
        self._executor.write_file(node, management_secret, self._settings.onx_node_agent_timer_path, agent_timer)
        code, _, stderr = self._executor.run(
            node,
            management_secret,
            "sh -lc 'systemctl daemon-reload && systemctl enable --now onx-node-agent.timer'",
        )
        if code != 0:
            raise RuntimeError(stderr or f"Failed to enable node agent on node {node.name}")
        return {
            "installed": True,
            "report_url": report_url,
            "interval_seconds": max(15, int(self._settings.onx_node_agent_interval_seconds)),
            "service_path": self._settings.onx_node_agent_service_path,
            "timer_path": self._settings.onx_node_agent_timer_path,
            "agent_path": self._settings.onx_node_agent_path,
        }

    def ensure_security_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        remote_script_path = "/tmp/onx-install-security-stack.sh"
        script_content = SECURITY_INSTALL_SCRIPT.replace("__ONX_NODE_SSH_PORT__", str(int(node.ssh_port)))
        self._executor.write_file(node, management_secret, remote_script_path, script_content)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install security stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
            "ssh_port_allowed": int(node.ssh_port),
            "ufw_enabled": True,
            "fail2ban_enabled": True,
        }

    def allow_public_port(
        self,
        node: Node,
        management_secret: str,
        *,
        port: int,
        protocol: str,
        comment: str | None = None,
    ) -> None:
        proto = str(protocol or "").strip().lower()
        if proto not in {"tcp", "udp"}:
            raise ValueError(f"Unsupported firewall protocol: {protocol}")
        port_value = int(port)
        if not 1 <= port_value <= 65535:
            raise ValueError(f"Firewall port out of range: {port}")
        comment_text = str(comment or "").strip()
        comment_fragment = ""
        if comment_text:
            safe_comment = comment_text.replace("'", "").replace('"', "")[:48]
            if safe_comment:
                comment_fragment = f" comment '{safe_comment}'"
        command = (
            "sh -lc "
            f"'command -v ufw >/dev/null 2>&1 || exit 0; "
            f"ufw allow {port_value}/{proto}{comment_fragment} >/dev/null 2>&1 || true'"
        )
        code, _, stderr = self._executor.run(node, management_secret, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to open {port_value}/{proto} via ufw on node {node.name}")

    def ensure_awg_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        script_content = (
            AWG_INSTALL_SCRIPT
            .replace("__AWG_TOOLS_REPO__", self._settings.onx_awg_tools_repo)
            .replace("__AWG_TOOLS_REF__", self._settings.onx_awg_tools_ref)
            .replace("__AWG_GO_REPO__", self._settings.onx_awg_go_repo)
            .replace("__AWG_GO_REF__", self._settings.onx_awg_go_ref)
            .replace("__GO_BOOTSTRAP_VERSION__", self._settings.onx_go_bootstrap_version)
        )
        remote_script_path = "/tmp/onx-install-awg-stack.sh"
        self._executor.write_file(node, management_secret, remote_script_path, script_content)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install AWG stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_wg_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        remote_script_path = "/tmp/onx-install-wg-stack.sh"
        self._executor.write_file(node, management_secret, remote_script_path, WG_INSTALL_SCRIPT)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install WG stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_openvpn_cloak_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        script_content = (
            OPENVPN_CLOAK_INSTALL_SCRIPT
            .replace("__CLOAK_VERSION__", self._settings.onx_cloak_version)
            .replace("__CLOAK_RELEASE_BASE_URL__", self._settings.onx_cloak_release_base_url.rstrip("/"))
        )
        remote_script_path = "/tmp/onx-install-openvpn-cloak-stack.sh"
        self._executor.write_file(node, management_secret, remote_script_path, script_content)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install OpenVPN+Cloak stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_xray_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        script_content = XRAY_INSTALL_SCRIPT.replace(
            "__XRAY_INSTALL_SCRIPT_URL__",
            self._settings.onx_xray_install_script_url,
        )
        remote_script_path = "/tmp/onx-install-xray-stack.sh"
        self._executor.write_file(node, management_secret, remote_script_path, script_content)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install Xray stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_transit_stack(self, node: Node, management_secret: str) -> dict:
        install_timeout = max(60, int(self._settings.ssh_install_timeout_seconds))
        remote_script_path = "/tmp/onx-install-transit-stack.sh"
        self._executor.write_file(node, management_secret, remote_script_path, TRANSIT_INSTALL_SCRIPT)
        code, stdout, stderr = self._executor.run(
            node,
            management_secret,
            f"sh -lc 'chmod 700 \"{remote_script_path}\" && \"{remote_script_path}\"; rm -f \"{remote_script_path}\"'",
            timeout_seconds=install_timeout,
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install transit stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def restart_interface(self, node: Node, management_secret: str, interface_name: str) -> None:
        service_name = f"onx-link@{interface_name}.service"
        command = (
            "sh -lc "
            f"'systemctl enable {service_name} >/dev/null 2>&1 || true; "
            f"systemctl restart {service_name}'"
        )
        code, _, stderr = self._executor.run(node, management_secret, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to restart {service_name} on node {node.name}")

    def stop_interface(self, node: Node, management_secret: str, interface_name: str) -> None:
        service_name = f"onx-link@{interface_name}.service"
        self._executor.run(
            node,
            management_secret,
            f"sh -lc 'systemctl stop {service_name} >/dev/null 2>&1 || true'",
        )

    def restart_xray_service(self, node: Node, management_secret: str, service_name: str) -> None:
        unit_name = f"onx-xray@{service_name}.service"
        command = (
            "sh -lc "
            f"'systemctl enable {unit_name} >/dev/null 2>&1 || true; "
            f"systemctl restart {unit_name}'"
        )
        code, _, stderr = self._executor.run(node, management_secret, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to restart {unit_name} on node {node.name}")

    def stop_xray_service(self, node: Node, management_secret: str, service_name: str) -> None:
        unit_name = f"onx-xray@{service_name}.service"
        self._executor.run(
            node,
            management_secret,
            f"sh -lc 'systemctl stop {unit_name} >/dev/null 2>&1 || true'",
        )

    def restart_openvpn_cloak_service(self, node: Node, management_secret: str, service_name: str) -> None:
        openvpn_unit = f"onx-openvpn@{service_name}.service"
        cloak_unit = f"onx-cloak@{service_name}.service"
        command = (
            "sh -lc "
            f"'systemctl enable {openvpn_unit} >/dev/null 2>&1 || true; "
            f"systemctl enable {cloak_unit} >/dev/null 2>&1 || true; "
            f"systemctl restart {openvpn_unit}; "
            f"systemctl restart {cloak_unit}'"
        )
        code, _, stderr = self._executor.run(node, management_secret, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to restart OpenVPN+Cloak units for {service_name} on node {node.name}")

    def stop_openvpn_cloak_service(self, node: Node, management_secret: str, service_name: str) -> None:
        openvpn_unit = f"onx-openvpn@{service_name}.service"
        cloak_unit = f"onx-cloak@{service_name}.service"
        self._executor.run(
            node,
            management_secret,
            f"sh -lc 'systemctl stop {cloak_unit} >/dev/null 2>&1 || true; systemctl stop {openvpn_unit} >/dev/null 2>&1 || true'",
        )

    def restart_transit_policy(self, node: Node, management_secret: str, policy_id: str) -> None:
        unit_name = f"onx-transit@{policy_id}.service"
        command = (
            "sh -lc "
            f"'systemctl enable {unit_name} >/dev/null 2>&1 || true; "
            f"systemctl restart {unit_name}'"
        )
        code, _, stderr = self._executor.run(node, management_secret, command)
        if code != 0:
            raise RuntimeError(stderr or f"Failed to restart {unit_name} on node {node.name}")

    def stop_transit_policy(self, node: Node, management_secret: str, policy_id: str) -> None:
        unit_name = f"onx-transit@{policy_id}.service"
        self._executor.run(
            node,
            management_secret,
            f"sh -lc 'systemctl stop {unit_name} >/dev/null 2>&1 || true'",
        )
