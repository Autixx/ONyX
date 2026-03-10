from __future__ import annotations

import ipaddress
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.dns_policy import DNSPolicy
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.dns_policies import DNSPolicyCreate, DNSPolicyUpdate


class DNSPolicyConflictError(ValueError):
    pass


class DNSPolicyService:
    def list_policies(
        self,
        db: Session,
        *,
        route_policy_id: str | None = None,
    ) -> list[DNSPolicy]:
        query = select(DNSPolicy)
        if route_policy_id is not None:
            query = query.where(DNSPolicy.route_policy_id == route_policy_id)
        return list(
            db.scalars(
                query.order_by(DNSPolicy.created_at.desc())
            ).all()
        )

    def get_policy(self, db: Session, policy_id: str) -> DNSPolicy | None:
        return db.get(DNSPolicy, policy_id)

    def get_for_route_policy(self, db: Session, route_policy_id: str) -> DNSPolicy | None:
        return db.scalar(
            select(DNSPolicy).where(DNSPolicy.route_policy_id == route_policy_id)
        )

    def create_policy(self, db: Session, payload: DNSPolicyCreate) -> DNSPolicy:
        route_policy = db.get(RoutePolicy, payload.route_policy_id)
        if route_policy is None:
            raise ValueError("Route policy not found.")

        existing = self.get_for_route_policy(db, payload.route_policy_id)
        if existing is not None:
            raise DNSPolicyConflictError("DNS policy for this route policy already exists.")

        normalized = self._normalize_create(payload)
        policy = DNSPolicy(**normalized)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def update_policy(self, db: Session, policy: DNSPolicy, payload: DNSPolicyUpdate) -> DNSPolicy:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return policy

        normalized = self._normalize_update(policy, updates)
        for key, value in normalized.items():
            setattr(policy, key, value)

        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def delete_policy(self, db: Session, policy: DNSPolicy) -> None:
        if policy.applied_state:
            raise ValueError(
                "DNS policy has applied rules. Disable it and apply the parent route policy first."
            )
        db.delete(policy)
        db.commit()

    def _normalize_create(self, payload: DNSPolicyCreate) -> dict:
        data = payload.model_dump()
        data["dns_address"] = self.normalize_dns_address(data["dns_address"])
        data["capture_protocols"] = self._normalize_capture_protocols(data["capture_protocols"])
        data["capture_ports"] = self._normalize_ports(data["capture_ports"])
        data["exceptions_networks"] = self._normalize_ipv4_networks(data["exceptions_networks"])
        return data

    def _normalize_update(self, current: DNSPolicy, updates: dict) -> dict:
        normalized: dict = {}
        if "dns_address" in updates:
            normalized["dns_address"] = self.normalize_dns_address(updates["dns_address"])
        if "capture_protocols" in updates:
            normalized["capture_protocols"] = self._normalize_capture_protocols(updates["capture_protocols"])
        if "capture_ports" in updates:
            normalized["capture_ports"] = self._normalize_ports(updates["capture_ports"])
        if "exceptions_networks" in updates:
            normalized["exceptions_networks"] = self._normalize_ipv4_networks(updates["exceptions_networks"])
        for key, value in updates.items():
            if key not in normalized:
                normalized[key] = value

        merged_protocols = normalized.get("capture_protocols", current.capture_protocols)
        merged_ports = normalized.get("capture_ports", current.capture_ports)
        if not merged_protocols:
            raise ValueError("capture_protocols must not be empty.")
        if not merged_ports:
            raise ValueError("capture_ports must not be empty.")
        return normalized

    @staticmethod
    def normalize_dns_address(value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("dns_address must not be empty.")
        host, port = DNSPolicyService.parse_dns_address(raw)
        return f"{host}:{port}"

    @staticmethod
    def parse_dns_address(value: str) -> tuple[str, int]:
        raw = value.strip()
        if ":" not in raw:
            host_raw = raw
            port = 53
        else:
            if raw.count(":") != 1:
                raise ValueError("Only IPv4 dns_address is supported in v1 (format: x.x.x.x[:port]).")
            host_raw, port_raw = raw.rsplit(":", 1)
            if not port_raw.isdigit():
                raise ValueError("dns_address port must be numeric.")
            port = int(port_raw)
        if port < 1 or port > 65535:
            raise ValueError("dns_address port must be in range 1..65535.")

        try:
            host = ipaddress.ip_address(host_raw.strip())
        except ValueError as exc:
            raise ValueError("dns_address host must be a valid IP address.") from exc
        if host.version != 4:
            raise ValueError("Only IPv4 dns_address is supported in v1.")
        return str(host), port

    @staticmethod
    def _normalize_capture_protocols(values: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            protocol = str(value).strip().lower()
            if protocol not in {"udp", "tcp"}:
                raise ValueError("capture_protocols supports only 'udp' and 'tcp' in v1.")
            if protocol in seen:
                continue
            seen.add(protocol)
            normalized.append(protocol)
        if not normalized:
            raise ValueError("capture_protocols must not be empty.")
        return normalized

    @staticmethod
    def _normalize_ports(values: Iterable[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for raw in values:
            try:
                port = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("capture_ports must contain only integer values.") from exc
            if port < 1 or port > 65535:
                raise ValueError("capture_ports values must be in range 1..65535.")
            if port in seen:
                continue
            seen.add(port)
            normalized.append(port)
        if not normalized:
            raise ValueError("capture_ports must not be empty.")
        return normalized

    @staticmethod
    def _normalize_ipv4_networks(values: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            text = str(raw).strip()
            if not text:
                continue
            try:
                network = ipaddress.ip_network(text, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid network '{text}' in exceptions_networks.") from exc
            if network.version != 4:
                raise ValueError("Only IPv4 networks are supported in exceptions_networks for v1.")
            value = str(network)
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized
