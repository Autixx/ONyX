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

