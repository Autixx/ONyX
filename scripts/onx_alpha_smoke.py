#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import string
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


def _rand_suffix(length: int = 6) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@dataclass
class ApiResponse:
    status: int
    headers: dict[str, str]
    body: dict | list | str | None


class ApiClient:
    def __init__(self, base_url: str, timeout: float, bearer_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.bearer_token = bearer_token

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        expected_statuses: tuple[int, ...] = (200,),
        bearer_token: str | None = None,
    ) -> ApiResponse:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        token = self.bearer_token if bearer_token is None else bearer_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)

        status = 0
        response_headers: dict[str, str] = {}
        raw_body = ""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status = int(response.status)
                response_headers = {key: value for key, value in response.headers.items()}
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            response_headers = {key: value for key, value in exc.headers.items()}
            raw_body = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc

        parsed: dict | list | str | None
        if raw_body == "":
            parsed = None
        else:
            try:
                parsed = json.loads(raw_body)
            except json.JSONDecodeError:
                parsed = raw_body

        if status not in expected_statuses:
            raise RuntimeError(f"{method} {path} failed: HTTP {status}: {raw_body}")
        return ApiResponse(status=status, headers=response_headers, body=parsed)


def _require_dict(response: ApiResponse, context: str) -> dict:
    if not isinstance(response.body, dict):
        raise RuntimeError(f"{context} did not return a JSON object")
    return response.body


def ensure_node(
    admin_client: ApiClient,
    *,
    name: str,
    role: str,
    management_address: str,
    ssh_host: str,
) -> dict:
    response = admin_client.request(
        "POST",
        "/nodes",
        {
            "name": name,
            "role": role,
            "management_address": management_address,
            "ssh_host": ssh_host,
            "ssh_port": 22,
            "ssh_user": "root",
            "auth_type": "password",
        },
        expected_statuses=(201,),
    )
    node = _require_dict(response, f"create node {name}")
    patched = admin_client.request(
        "PATCH",
        f"/nodes/{node['id']}",
        {"status": "reachable"},
        expected_statuses=(200,),
    )
    return _require_dict(patched, f"patch node {name}")


def ensure_ingress_candidates(admin_client: ApiClient, min_count: int = 2) -> list[dict]:
    response = admin_client.request("GET", "/nodes", expected_statuses=(200,))
    nodes = response.body if isinstance(response.body, list) else []
    eligible = [
        node
        for node in nodes
        if node.get("role") in {"gateway", "mixed"} and node.get("status") != "offline"
    ]
    created: list[dict] = []
    while len(eligible) < min_count:
        suffix = _rand_suffix()
        node = ensure_node(
            admin_client,
            name=f"smoke-gw-{suffix}",
            role="gateway",
            management_address=f"198.51.100.{random.randint(10, 200)}:51820",
            ssh_host=f"198.51.100.{random.randint(10, 200)}",
        )
        eligible.append(node)
        created.append(node)
    return eligible[:min_count] + created


def create_test_topology(admin_client: ApiClient) -> tuple[dict, dict, dict]:
    suffix = _rand_suffix()
    left = ensure_node(
        admin_client,
        name=f"smoke-path-left-{suffix}",
        role="gateway",
        management_address=f"203.0.113.{random.randint(10, 200)}:51820",
        ssh_host=f"203.0.113.{random.randint(10, 200)}",
    )
    right = ensure_node(
        admin_client,
        name=f"smoke-path-right-{suffix}",
        role="egress",
        management_address=f"198.18.0.{random.randint(10, 200)}:51820",
        ssh_host=f"198.18.0.{random.randint(10, 200)}",
    )

    link_response = admin_client.request(
        "POST",
        "/links",
        {
            "name": f"smoke-link-{suffix}",
            "driver_name": "awg",
            "topology_type": "p2p",
            "left_node_id": left["id"],
            "right_node_id": right["id"],
            "spec": {
                "mode": "site_to_site",
                "left": {
                    "interface_name": f"awg-smk-l-{suffix[:4]}",
                    "listen_port": random.randint(20000, 25000),
                    "address_v4": "10.250.0.1/30",
                    "mtu": 1420,
                    "endpoint_host": left["ssh_host"],
                },
                "right": {
                    "interface_name": f"awg-smk-r-{suffix[:4]}",
                    "listen_port": random.randint(25001, 29999),
                    "address_v4": "10.250.0.2/30",
                    "mtu": 1420,
                    "endpoint_host": right["ssh_host"],
                },
                "peer": {
                    "persistent_keepalive": 21,
                    "mtu": 1420,
                    "left_allowed_ips": ["0.0.0.0/0"],
                    "right_allowed_ips": [],
                },
                "awg_obfuscation": {
                    "jc": 4,
                    "jmin": 40,
                    "jmax": 120,
                    "s1": 10,
                    "s2": 20,
                    "s3": 30,
                    "s4": 40,
                    "h1": 10101,
                    "h2": 20202,
                    "h3": 30303,
                    "h4": 40404,
                },
            },
        },
        expected_statuses=(201,),
    )
    link = _require_dict(link_response, "create test link")
    return left, right, link


def check_client_auth_enforcement(client: ApiClient) -> None:
    response = client.request(
        "POST",
        "/bootstrap",
        {
            "device_id": f"smoke-auth-{_rand_suffix()}",
            "candidate_limit": 1,
        },
        expected_statuses=(401,),
        bearer_token="",
    )
    payload = _require_dict(response, "auth check")
    if "Bearer" not in response.headers.get("WWW-Authenticate", ""):
        raise RuntimeError("401 client auth check is missing WWW-Authenticate: Bearer")
    if not payload.get("detail"):
        raise RuntimeError("401 client auth check returned empty detail")


def check_admin_auth_enforcement(client: ApiClient) -> None:
    response = client.request(
        "GET",
        "/nodes",
        expected_statuses=(401,),
        bearer_token="",
    )
    payload = _require_dict(response, "admin auth check")
    if "Bearer" not in response.headers.get("WWW-Authenticate", ""):
        raise RuntimeError("401 admin auth check is missing WWW-Authenticate: Bearer")
    if not payload.get("detail"):
        raise RuntimeError("401 admin auth check returned empty detail")


def main() -> int:
    parser = argparse.ArgumentParser(description="ONX alpha smoke test")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8081/api/v1",
        help="Base ONX API URL (default: http://127.0.0.1:8081/api/v1)",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--client-bearer-token",
        default=None,
        help="Bearer token or JWT for protected client-routing endpoints",
    )
    parser.add_argument(
        "--admin-bearer-token",
        default=None,
        help="Bearer token or JWT for protected admin/control-plane endpoints",
    )
    parser.add_argument(
        "--expect-auth",
        action="store_true",
        help="Expect client-routing endpoints to reject unauthenticated requests with 401",
    )
    parser.add_argument(
        "--check-rate-limit",
        action="store_true",
        help="Check that repeated session-rebind triggers 429 with Retry-After",
    )
    args = parser.parse_args()

    client = ApiClient(args.base_url, timeout=args.timeout, bearer_token=args.client_bearer_token)
    admin_client = ApiClient(args.base_url, timeout=args.timeout, bearer_token=args.admin_bearer_token)
    unauth_client = ApiClient(args.base_url, timeout=args.timeout)

    try:
        if args.expect_auth:
            check_client_auth_enforcement(unauth_client)
            check_admin_auth_enforcement(unauth_client)
            if not args.client_bearer_token:
                raise RuntimeError("--expect-auth requires --client-bearer-token for the client flow")
            if not args.admin_bearer_token:
                raise RuntimeError("--expect-auth requires --admin-bearer-token for the admin flow")

        health = _require_dict(client.request("GET", "/health", expected_statuses=(200,)), "health")
        if health.get("status") != "ok":
            raise RuntimeError("Health endpoint did not return status=ok")

        ingress_candidates = ensure_ingress_candidates(admin_client, min_count=2)
        print(f"[smoke] ingress candidates available: {len(ingress_candidates)}")

        left_node, right_node, link = create_test_topology(admin_client)
        print(f"[smoke] test topology created: {left_node['name']} -> {right_node['name']}")

        bootstrap = _require_dict(
            client.request(
                "POST",
                "/bootstrap",
                {
                    "device_id": f"smoke-device-{_rand_suffix()}",
                    "client_public_ip": "203.0.113.50",
                    "client_country_code": "RU",
                    "destination_country_code": "US",
                    "candidate_limit": 4,
                    "metadata": {"source": "alpha-smoke"},
                },
                expected_statuses=(200,),
            ),
            "bootstrap",
        )
        session_id = bootstrap["session_id"]
        session_token = bootstrap["session_token"]
        probe_targets = bootstrap.get("probe_targets", [])
        if not probe_targets:
            raise RuntimeError("Bootstrap returned empty probe_targets")

        measurements: list[dict] = []
        for i, item in enumerate(probe_targets[:2]):
            measurements.append(
                {
                    "node_id": item["node_id"],
                    "rtt_ms": 25.0 + i * 25.0,
                    "jitter_ms": 2.0 + i * 2.0,
                    "loss_pct": 0.1 + i * 0.8,
                    "handshake_ms": 14.0 + i * 15.0,
                    "throughput_mbps": 190.0 - i * 35.0,
                    "raw": {
                        "sample_ts": datetime.now(timezone.utc).isoformat(),
                        "probe_seq": i + 1,
                    },
                }
            )

        probe_result = _require_dict(
            client.request(
                "POST",
                "/probe",
                {
                    "session_id": session_id,
                    "session_token": session_token,
                    "measurements": measurements,
                },
                expected_statuses=(200,),
            ),
            "probe",
        )
        if int(probe_result.get("accepted", 0)) < 1:
            raise RuntimeError("Probe report did not accept any measurements")

        decision = _require_dict(
            client.request(
                "POST",
                "/best-ingress",
                {
                    "session_id": session_id,
                    "session_token": session_token,
                    "require_fresh_probe": True,
                    "max_candidates": 3,
                    "plan_path": False,
                },
                expected_statuses=(200,),
            ),
            "best-ingress",
        )
        selected = decision.get("selected", {})
        if not selected.get("node_id"):
            raise RuntimeError("best-ingress response has no selected node_id")

        graph = _require_dict(admin_client.request("GET", "/graph", expected_statuses=(200,)), "graph")
        if len(graph.get("nodes", [])) < 2:
            raise RuntimeError("graph returned too few nodes")
        if not any(edge.get("id") == link["id"] for edge in graph.get("edges", [])):
            raise RuntimeError("graph does not include the smoke test link")

        path_plan = _require_dict(
            admin_client.request(
                "POST",
                "/paths/plan",
                {
                    "source_node_id": left_node["id"],
                    "destination_node_id": right_node["id"],
                    "require_active_links": False,
                    "max_hops": 4,
                },
                expected_statuses=(200,),
            ),
            "paths/plan",
        )
        node_path = path_plan.get("node_path", [])
        if node_path != [left_node["id"], right_node["id"]]:
            raise RuntimeError(f"unexpected node_path from planner: {node_path}")

        rebind = _require_dict(
            client.request(
                "POST",
                "/session-rebind",
                {
                    "session_id": session_id,
                    "session_token": session_token,
                    "force": True,
                },
                expected_statuses=(200,),
            ),
            "session-rebind",
        )
        if not rebind.get("current_node_id"):
            raise RuntimeError("session-rebind response has no current_node_id")

        if args.check_rate_limit:
            if not args.client_bearer_token:
                raise RuntimeError("--check-rate-limit requires --client-bearer-token")
            limited_response = client.request(
                "POST",
                "/session-rebind",
                {
                    "session_id": session_id,
                    "session_token": session_token,
                    "force": True,
                },
                expected_statuses=(429,),
            )
            limited = _require_dict(limited_response, "session-rebind rate-limit check")
            if not limited.get("detail"):
                raise RuntimeError("429 response is missing detail")
            retry_after = limited_response.headers.get("Retry-After", "")
            if not retry_after.isdigit() or int(retry_after) < 1:
                raise RuntimeError("429 response is missing valid Retry-After header")

        print("[smoke] OK")
        print(f"[smoke] selected ingress: {selected.get('node_name')} ({selected.get('node_id')})")
        print(f"[smoke] path score: {path_plan.get('total_score')}")
        print(f"[smoke] rebind reason: {rebind.get('reason')}")
        return 0
    except Exception as exc:
        print(f"[smoke] FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
