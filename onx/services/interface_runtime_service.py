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
    CONF_DIR="${ONX_AWG_CONF_DIR:-__ONX_CONF_DIR__}"
    CONF_PATH="${CONF_DIR}/${IFACE}.conf"

    if [[ -z "${ACTION}" || -z "${IFACE}" ]]; then
      echo "usage: onx-link-runner <up|down|reload|status> <iface>" >&2
      exit 2
    fi

    case "${ACTION}" in
      up)
        awg-quick down "${IFACE}" >/dev/null 2>&1 || true
        awg-quick up "${CONF_PATH}"
        ;;
      down)
        awg-quick down "${IFACE}" >/dev/null 2>&1 || true
        ;;
      reload)
        awg-quick down "${IFACE}" >/dev/null 2>&1 || true
        awg-quick up "${CONF_PATH}"
        ;;
      status)
        awg show "${IFACE}"
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
    Description=ONX managed AWG interface %i
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


class InterfaceRuntimeService:
    def __init__(self, executor: SSHExecutor) -> None:
        self._executor = executor
        self._settings = get_settings()

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

    def ensure_awg_stack(self, node: Node, management_secret: str) -> dict:
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
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install AWG stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_openvpn_cloak_stack(self, node: Node, management_secret: str) -> dict:
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
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install OpenVPN+Cloak stack on node {node.name}")
        return {
            "installed": True,
            "stdout": stdout,
        }

    def ensure_xray_stack(self, node: Node, management_secret: str) -> dict:
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
        )
        if code != 0:
            raise RuntimeError(stderr or stdout or f"Failed to install Xray stack on node {node.name}")
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
