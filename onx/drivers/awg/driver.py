import ipaddress
import re
from typing import Any

from onx.drivers.base import DriverBase, DriverValidationResult


class AWGDriver(DriverBase):
    name = "awg"

    REQUIRED_CAPABILITIES = ("awg", "awg_quick", "amneziawg_go", "iptables", "systemctl")

    def _validate_endpoint(self, endpoint_spec: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        try:
            ipaddress.ip_interface(endpoint_spec["address_v4"])
        except Exception as exc:
            raise ValueError(f"Invalid address_v4 '{endpoint_spec['address_v4']}': {exc}") from exc

        interface_name = str(endpoint_spec["interface_name"]).strip()
        if len(interface_name) == 0:
            raise ValueError("interface_name cannot be empty")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", interface_name):
            raise ValueError("interface_name must match [A-Za-z0-9_.-]{1,32}")

        if not 1 <= int(endpoint_spec["listen_port"]) <= 65535:
            raise ValueError("listen_port must be in range 1..65535")

        return warnings

    def _render_preview(self, spec: dict[str, Any]) -> dict[str, str]:
        return self.render_runtime(
            spec=spec,
            left_public_key="<generated-on-apply>",
            right_public_key="<generated-on-apply>",
        )

    def render_runtime(
        self,
        spec: dict[str, Any],
        left_public_key: str,
        right_public_key: str,
    ) -> dict[str, str]:
        left = spec["left"]
        right = spec["right"]
        obf = spec["awg_obfuscation"]
        peer = spec["peer"]

        left_preview = "\n".join([
            "[Interface]",
            f"Address = {left['address_v4']}",
            f"ListenPort = {left['listen_port']}",
            f"Jc = {obf['jc']}",
            f"Jmin = {obf['jmin']}",
            f"Jmax = {obf['jmax']}",
            f"S1 = {obf['s1']}",
            f"S2 = {obf['s2']}",
            f"S3 = {obf['s3']}",
            f"S4 = {obf['s4']}",
            f"H1 = {obf['h1']}",
            f"H2 = {obf['h2']}",
            f"H3 = {obf['h3']}",
            f"H4 = {obf['h4']}",
            "",
            "[Peer]",
            f"PublicKey = {right_public_key}",
            f"AllowedIPs = {','.join(peer['left_allowed_ips'])}",
            f"Endpoint = {right['endpoint_host']}:{right['listen_port']}",
            f"PersistentKeepalive = {peer['persistent_keepalive']}",
        ])

        right_allowed_ips = peer["right_allowed_ips"] or [
            str(ipaddress.ip_interface(left["address_v4"]).ip) + "/32"
        ]
        right_preview = "\n".join([
            "[Interface]",
            f"Address = {right['address_v4']}",
            f"ListenPort = {right['listen_port']}",
            f"Jc = {obf['jc']}",
            f"Jmin = {obf['jmin']}",
            f"Jmax = {obf['jmax']}",
            f"S1 = {obf['s1']}",
            f"S2 = {obf['s2']}",
            f"S3 = {obf['s3']}",
            f"S4 = {obf['s4']}",
            f"H1 = {obf['h1']}",
            f"H2 = {obf['h2']}",
            f"H3 = {obf['h3']}",
            f"H4 = {obf['h4']}",
            "",
            "[Peer]",
            f"PublicKey = {left_public_key}",
            f"AllowedIPs = {','.join(right_allowed_ips)}",
            f"Endpoint = {left['endpoint_host']}:{left['listen_port']}",
            f"PersistentKeepalive = {peer['persistent_keepalive']}",
        ])
        return {"left": left_preview, "right": right_preview}

    def validate(self, spec: dict[str, Any], context: dict[str, Any]) -> DriverValidationResult:
        warnings: list[str] = []
        self._validate_endpoint(spec["left"])
        self._validate_endpoint(spec["right"])

        left_capabilities = context["left_capabilities"]
        right_capabilities = context["right_capabilities"]

        missing: list[str] = []
        for side_name, caps in (("left", left_capabilities), ("right", right_capabilities)):
            supported = {cap["capability_name"] for cap in caps if cap["supported"]}
            for required in self.REQUIRED_CAPABILITIES:
                if required not in supported:
                    missing.append(f"{side_name}:{required}")

        if missing:
            raise ValueError("Missing required capabilities: " + ", ".join(missing))

        return DriverValidationResult({
            "valid": True,
            "warnings": warnings,
            "render_preview": self._render_preview(spec),
        })
