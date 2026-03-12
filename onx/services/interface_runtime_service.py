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

    fail() {
      echo "$*" >&2
      exit 1
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
      rm -rf /usr/local/go
      tar -C /usr/local -xzf "${tarball}"
      rm -f "${tarball}"
      ln -sf /usr/local/go/bin/go /usr/local/bin/go
      ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt
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

      apt-get update
      apt-get install -y \
        ca-certificates \
        curl \
        git \
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
        make -C "${tools_dir}/src" -j"${make_jobs}" install WITH_WGQUICK=yes WITH_SYSTEMDUNITS=yes
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
        make -C "${go_dir}" -j"${make_jobs}" install
      fi

      rm -rf "${build_root}"

      command -v awg >/dev/null 2>&1 || fail "[awg] Install failed: awg not found."
      command -v awg-quick >/dev/null 2>&1 || fail "[awg] Install failed: awg-quick not found."
      command -v amneziawg-go >/dev/null 2>&1 || fail "[awg] Install failed: amneziawg-go not found."
      command -v iptables >/dev/null 2>&1 || fail "[awg] Install failed: iptables not found."
      command -v ipset >/dev/null 2>&1 || fail "[awg] Install failed: ipset not found."
      command -v systemctl >/dev/null 2>&1 || fail "[awg] Install failed: systemctl not found."
    }

    install_awg_stack
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
