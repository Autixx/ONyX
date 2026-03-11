from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.balancer import Balancer
from onx.db.models.dns_policy import DNSPolicy
from onx.db.models.event_log import EventLevel
from onx.db.models.geo_policy import GeoPolicy
from onx.db.models.link import Link, LinkState
from onx.db.models.link_endpoint import LinkEndpoint, LinkSide
from onx.db.models.node import Node, NodeStatus
from onx.db.models.node_secret import NodeSecret, NodeSecretKind
from onx.db.models.route_policy import RoutePolicy
from onx.schemas.balancers import BalancerCreate, BalancerUpdate
from onx.schemas.dns_policies import DNSPolicyCreate, DNSPolicyUpdate
from onx.schemas.geo_policies import GeoPolicyCreate, GeoPolicyUpdate
from onx.schemas.links import LinkCreate
from onx.schemas.nodes import NodeCreate, NodeUpdate
from onx.schemas.route_policies import RoutePolicyCreate, RoutePolicyUpdate
from onx.services.balancer_service import BalancerService
from onx.services.dns_policy_service import DNSPolicyService
from onx.services.event_log_service import EventLogService
from onx.services.geo_policy_service import GeoPolicyService
from onx.services.link_service import LinkService
from onx.services.route_policy_service import RoutePolicyService
from onx.services.secret_service import SecretService


class ControlPlaneStateService:
    def __init__(self) -> None:
        self._balancers = BalancerService()
        self._dns_policies = DNSPolicyService()
        self._events = EventLogService()
        self._geo_policies = GeoPolicyService()
        self._links = LinkService()
        self._route_policies = RoutePolicyService()
        self._secrets = SecretService()

    def export_state(self, db: Session, *, include_management_secrets: bool = False) -> dict:
        node_secrets_by_node: dict[str, list[dict]] = {}
        if include_management_secrets:
            for secret in db.scalars(
                select(NodeSecret).where(
                    NodeSecret.is_active.is_(True),
                    NodeSecret.kind.in_([NodeSecretKind.SSH_PASSWORD, NodeSecretKind.SSH_PRIVATE_KEY]),
                )
            ).all():
                node_secrets_by_node.setdefault(secret.node_id, []).append(
                    {
                        "kind": secret.kind.value,
                        "value": self._secrets.decrypt(secret.encrypted_value),
                    }
                )

        nodes = list(db.scalars(select(Node).order_by(Node.name.asc())).all())
        node_names = {node.id: node.name for node in nodes}
        route_policies = list(db.scalars(select(RoutePolicy).order_by(RoutePolicy.node_id.asc(), RoutePolicy.name.asc())).all())
        balancers = list(db.scalars(select(Balancer).order_by(Balancer.node_id.asc(), Balancer.name.asc())).all())
        balancer_name_by_id = {balancer.id: balancer.name for balancer in balancers}
        route_policy_ref_by_id = {
            policy.id: {"node_name": node_names.get(policy.node_id), "route_policy_name": policy.name}
            for policy in route_policies
        }

        return {
            "version": 1,
            "kind": "control_plane_state",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "includes": {
                "management_secrets": include_management_secrets,
                "transport_private_keys": False,
            },
            "nodes": [
                {
                    "name": node.name,
                    "role": node.role.value,
                    "management_address": node.management_address,
                    "ssh_host": node.ssh_host,
                    "ssh_port": node.ssh_port,
                    "ssh_user": node.ssh_user,
                    "auth_type": node.auth_type.value,
                    "management_secrets": node_secrets_by_node.get(node.id, []),
                }
                for node in nodes
            ],
            "links": [
                {
                    "name": link.name,
                    "driver_name": link.driver_name,
                    "topology_type": link.topology_type.value,
                    "left_node_name": node_names.get(link.left_node_id),
                    "right_node_name": node_names.get(link.right_node_id),
                    "spec": dict(link.desired_spec_json or {}),
                }
                for link in db.scalars(select(Link).order_by(Link.name.asc())).all()
            ],
            "balancers": [
                {
                    "node_name": node_names.get(balancer.node_id),
                    "name": balancer.name,
                    "method": balancer.method.value,
                    "members": list(balancer.members or []),
                    "enabled": balancer.enabled,
                }
                for balancer in balancers
            ],
            "route_policies": [
                {
                    "node_name": node_names.get(policy.node_id),
                    "name": policy.name,
                    "ingress_interface": policy.ingress_interface,
                    "action": policy.action.value,
                    "target_interface": policy.target_interface,
                    "target_gateway": policy.target_gateway,
                    "balancer_name": balancer_name_by_id.get(policy.balancer_id) if policy.balancer_id else None,
                    "routed_networks": list(policy.routed_networks or []),
                    "excluded_networks": list(policy.excluded_networks or []),
                    "table_id": policy.table_id,
                    "rule_priority": policy.rule_priority,
                    "firewall_mark": policy.firewall_mark,
                    "masquerade": policy.masquerade,
                    "enabled": policy.enabled,
                }
                for policy in route_policies
            ],
            "dns_policies": [
                {
                    "route_policy_ref": route_policy_ref_by_id.get(policy.route_policy_id),
                    "enabled": policy.enabled,
                    "dns_address": policy.dns_address,
                    "capture_protocols": list(policy.capture_protocols or []),
                    "capture_ports": list(policy.capture_ports or []),
                    "exceptions_networks": list(policy.exceptions_networks or []),
                }
                for policy in db.scalars(select(DNSPolicy).order_by(DNSPolicy.created_at.asc())).all()
            ],
            "geo_policies": [
                {
                    "route_policy_ref": route_policy_ref_by_id.get(policy.route_policy_id),
                    "country_code": policy.country_code,
                    "mode": policy.mode.value,
                    "source_url_template": policy.source_url_template,
                    "enabled": policy.enabled,
                }
                for policy in db.scalars(select(GeoPolicy).order_by(GeoPolicy.created_at.asc(), GeoPolicy.country_code.asc())).all()
            ],
        }

    def import_state(self, db: Session, document: dict, *, replace: bool = False) -> dict:
        if not isinstance(document, dict):
            raise ValueError("Input JSON must be an object.")

        nodes_data = list(document.get("nodes") or [])
        links_data = list(document.get("links") or [])
        balancers_data = list(document.get("balancers") or [])
        route_policies_data = list(document.get("route_policies") or [])
        dns_policies_data = list(document.get("dns_policies") or [])
        geo_policies_data = list(document.get("geo_policies") or [])

        upsert_counts = {
            "nodes": 0,
            "links": 0,
            "balancers": 0,
            "route_policies": 0,
            "dns_policies": 0,
            "geo_policies": 0,
            "management_secrets": 0,
        }

        node_by_name: dict[str, Node] = {}
        for item in nodes_data:
            node = self._upsert_node(db, item)
            node_by_name[node.name] = node
            upsert_counts["nodes"] += 1
            upsert_counts["management_secrets"] += self._upsert_management_secrets(db, node, item.get("management_secrets") or [])

        for item in balancers_data:
            self._upsert_balancer(db, node_by_name, item)
            upsert_counts["balancers"] += 1

        balancer_by_ref = {
            (node.name, balancer.name): balancer
            for balancer in db.scalars(select(Balancer)).all()
            for node in [db.get(Node, balancer.node_id)]
            if node is not None
        }

        route_policy_by_ref: dict[tuple[str, str], RoutePolicy] = {}
        for item in route_policies_data:
            policy = self._upsert_route_policy(db, node_by_name, balancer_by_ref, item)
            route_policy_by_ref[(item["node_name"], item["name"])] = policy
            upsert_counts["route_policies"] += 1

        for item in dns_policies_data:
            self._upsert_dns_policy(db, route_policy_by_ref, item)
            upsert_counts["dns_policies"] += 1

        for item in geo_policies_data:
            self._upsert_geo_policy(db, route_policy_by_ref, item)
            upsert_counts["geo_policies"] += 1

        for item in links_data:
            self._upsert_link(db, node_by_name, item)
            upsert_counts["links"] += 1

        deleted = self._replace_missing(
            db,
            replace=replace,
            nodes_data=nodes_data,
            links_data=links_data,
            balancers_data=balancers_data,
            route_policies_data=route_policies_data,
            dns_policies_data=dns_policies_data,
            geo_policies_data=geo_policies_data,
        )

        self._events.log(
            db,
            entity_type="control_plane_state",
            entity_id="import",
            level=EventLevel.INFO,
            message="Control-plane state imported.",
            details={
                "replace": bool(replace),
                "upsert_counts": upsert_counts,
                "deleted": deleted,
            },
        )
        return {
            "status": "ok",
            "upsert_counts": upsert_counts,
            "deleted": deleted,
        }

    def _upsert_node(self, db: Session, item: dict) -> Node:
        payload = NodeCreate(
            name=item["name"],
            role=item["role"],
            management_address=item["management_address"],
            ssh_host=item["ssh_host"],
            ssh_port=item.get("ssh_port", 22),
            ssh_user=item["ssh_user"],
            auth_type=item["auth_type"],
        )
        node = db.scalar(select(Node).where(Node.name == payload.name))
        if node is None:
            node = Node(**payload.model_dump())
            db.add(node)
            db.commit()
            db.refresh(node)
            return node

        updated = NodeUpdate(**payload.model_dump())
        for key, value in updated.model_dump(exclude_unset=True).items():
            setattr(node, key, value)
        node.status = NodeStatus.UNKNOWN
        db.add(node)
        db.commit()
        db.refresh(node)
        return node

    def _upsert_management_secrets(self, db: Session, node: Node, secrets: list[dict]) -> int:
        count = 0
        expected_kind = (
            NodeSecretKind.SSH_PASSWORD
            if node.auth_type.value == "password"
            else NodeSecretKind.SSH_PRIVATE_KEY
        )
        for secret_item in secrets:
            kind = NodeSecretKind(str(secret_item["kind"]))
            if kind not in {NodeSecretKind.SSH_PASSWORD, NodeSecretKind.SSH_PRIVATE_KEY}:
                continue
            if kind != expected_kind:
                raise ValueError(
                    f"Node '{node.name}' expects management secret kind '{expected_kind.value}', got '{kind.value}'."
                )
            self._secrets.upsert_node_secret(db, node.id, kind, str(secret_item["value"]))
            db.commit()
            count += 1
        return count

    def _upsert_balancer(self, db: Session, node_by_name: dict[str, Node], item: dict) -> Balancer:
        node_name = str(item["node_name"])
        node = node_by_name.get(node_name)
        if node is None:
            raise ValueError(f"Balancer references unknown node '{node_name}'.")
        payload = BalancerCreate(
            node_id=node.id,
            name=item["name"],
            method=item["method"],
            members=item["members"],
            enabled=bool(item.get("enabled", True)),
        )
        existing = db.scalar(select(Balancer).where(Balancer.node_id == node.id, Balancer.name == payload.name))
        if existing is None:
            return self._balancers.create_balancer(db, payload)

        balancer = self._balancers.update_balancer(
            db,
            existing,
            BalancerUpdate(
                name=payload.name,
                method=payload.method,
                members=payload.members,
                enabled=payload.enabled,
            ),
        )
        balancer.state_json = None
        db.add(balancer)
        db.commit()
        db.refresh(balancer)
        return balancer

    def _upsert_route_policy(
        self,
        db: Session,
        node_by_name: dict[str, Node],
        balancer_by_ref: dict[tuple[str, str], Balancer],
        item: dict,
    ) -> RoutePolicy:
        node_name = str(item["node_name"])
        node = node_by_name.get(node_name)
        if node is None:
            raise ValueError(f"Route policy references unknown node '{node_name}'.")
        balancer_id = None
        balancer_name = item.get("balancer_name")
        if balancer_name:
            balancer = balancer_by_ref.get((node_name, str(balancer_name)))
            if balancer is None:
                raise ValueError(
                    f"Route policy '{item['name']}' references unknown balancer '{balancer_name}' on node '{node_name}'."
                )
            balancer_id = balancer.id
        payload = RoutePolicyCreate(
            node_id=node.id,
            name=item["name"],
            ingress_interface=item["ingress_interface"],
            action=item["action"],
            target_interface=item.get("target_interface"),
            target_gateway=item.get("target_gateway"),
            balancer_id=balancer_id,
            routed_networks=list(item.get("routed_networks") or []),
            excluded_networks=list(item.get("excluded_networks") or []),
            table_id=int(item.get("table_id", 51820)),
            rule_priority=int(item.get("rule_priority", 10000)),
            firewall_mark=int(item.get("firewall_mark", 51820)),
            masquerade=bool(item.get("masquerade", True)),
            enabled=bool(item.get("enabled", True)),
        )
        existing = db.scalar(select(RoutePolicy).where(RoutePolicy.node_id == node.id, RoutePolicy.name == payload.name))
        if existing is None:
            return self._route_policies.create_policy(db, payload)

        policy = self._route_policies.update_policy(
            db,
            existing,
            RoutePolicyUpdate(
                name=payload.name,
                ingress_interface=payload.ingress_interface,
                action=payload.action,
                target_interface=payload.target_interface,
                target_gateway=payload.target_gateway,
                balancer_id=payload.balancer_id,
                routed_networks=payload.routed_networks,
                excluded_networks=payload.excluded_networks,
                table_id=payload.table_id,
                rule_priority=payload.rule_priority,
                firewall_mark=payload.firewall_mark,
                masquerade=payload.masquerade,
                enabled=payload.enabled,
            ),
        )
        policy.applied_state = None
        policy.last_applied_at = None
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def _upsert_dns_policy(self, db: Session, route_policy_by_ref: dict[tuple[str, str], RoutePolicy], item: dict) -> DNSPolicy:
        route_ref = item.get("route_policy_ref") or {}
        key = (str(route_ref.get("node_name") or ""), str(route_ref.get("route_policy_name") or ""))
        route_policy = route_policy_by_ref.get(key)
        if route_policy is None:
            raise ValueError(f"DNS policy references unknown route policy '{key[0]}/{key[1]}'.")
        payload = DNSPolicyCreate(
            route_policy_id=route_policy.id,
            enabled=bool(item.get("enabled", False)),
            dns_address=item["dns_address"],
            capture_protocols=list(item.get("capture_protocols") or []),
            capture_ports=list(item.get("capture_ports") or []),
            exceptions_networks=list(item.get("exceptions_networks") or []),
        )
        existing = self._dns_policies.get_for_route_policy(db, route_policy.id)
        if existing is None:
            return self._dns_policies.create_policy(db, payload)

        policy = self._dns_policies.update_policy(
            db,
            existing,
            DNSPolicyUpdate(
                enabled=payload.enabled,
                dns_address=payload.dns_address,
                capture_protocols=payload.capture_protocols,
                capture_ports=payload.capture_ports,
                exceptions_networks=payload.exceptions_networks,
            ),
        )
        policy.applied_state = None
        policy.last_applied_at = None
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    def _upsert_geo_policy(self, db: Session, route_policy_by_ref: dict[tuple[str, str], RoutePolicy], item: dict) -> GeoPolicy:
        route_ref = item.get("route_policy_ref") or {}
        key = (str(route_ref.get("node_name") or ""), str(route_ref.get("route_policy_name") or ""))
        route_policy = route_policy_by_ref.get(key)
        if route_policy is None:
            raise ValueError(f"Geo policy references unknown route policy '{key[0]}/{key[1]}'.")
        payload = GeoPolicyCreate(
            route_policy_id=route_policy.id,
            country_code=item["country_code"],
            mode=item.get("mode", "direct"),
            source_url_template=item.get("source_url_template"),
            enabled=bool(item.get("enabled", True)),
        )
        existing = db.scalar(
            select(GeoPolicy).where(
                GeoPolicy.route_policy_id == route_policy.id,
                GeoPolicy.country_code == str(item["country_code"]).strip().lower(),
            )
        )
        if existing is None:
            return self._geo_policies.create_policy(db, payload)

        return self._geo_policies.update_policy(
            db,
            existing,
            GeoPolicyUpdate(
                country_code=payload.country_code,
                mode=payload.mode,
                source_url_template=payload.source_url_template,
                enabled=payload.enabled,
            ),
        )

    def _upsert_link(self, db: Session, node_by_name: dict[str, Node], item: dict) -> Link:
        left_node_name = str(item["left_node_name"])
        right_node_name = str(item["right_node_name"])
        left_node = node_by_name.get(left_node_name)
        right_node = node_by_name.get(right_node_name)
        if left_node is None or right_node is None:
            raise ValueError(f"Link '{item['name']}' references unknown nodes.")
        payload = LinkCreate(
            name=item["name"],
            driver_name=item["driver_name"],
            topology_type=item.get("topology_type", "p2p"),
            left_node_id=left_node.id,
            right_node_id=right_node.id,
            spec=item["spec"],
        )
        existing = db.scalar(select(Link).where(Link.name == payload.name))
        if existing is None:
            return self._links.create_link(db, payload)

        existing.driver_name = payload.driver_name.value
        existing.topology_type = payload.topology_type.value
        existing.left_node_id = payload.left_node_id
        existing.right_node_id = payload.right_node_id
        existing.desired_spec_json = payload.spec.model_dump()
        existing.applied_spec_json = None
        existing.health_summary_json = None
        existing.state = LinkState.PLANNED
        db.add(existing)
        db.flush()

        for side, node_id, endpoint_spec in (
            (LinkSide.LEFT, payload.left_node_id, payload.spec.left),
            (LinkSide.RIGHT, payload.right_node_id, payload.spec.right),
        ):
            endpoint = db.scalar(select(LinkEndpoint).where(LinkEndpoint.link_id == existing.id, LinkEndpoint.side == side))
            if endpoint is None:
                endpoint = LinkEndpoint(link_id=existing.id, node_id=node_id, side=side)
            endpoint.node_id = node_id
            endpoint.interface_name = endpoint_spec.interface_name
            endpoint.listen_port = endpoint_spec.listen_port
            endpoint.address_v4 = endpoint_spec.address_v4
            endpoint.address_v6 = endpoint_spec.address_v6
            endpoint.mtu = endpoint_spec.mtu
            endpoint.endpoint = f"{endpoint_spec.endpoint_host}:{endpoint_spec.listen_port}"
            endpoint.public_key = None
            endpoint.private_key_secret_ref = None
            endpoint.rendered_config = None
            endpoint.applied_state_json = None
            db.add(endpoint)
        db.commit()
        db.refresh(existing)
        return existing

    def _replace_missing(
        self,
        db: Session,
        *,
        replace: bool,
        nodes_data: list[dict],
        links_data: list[dict],
        balancers_data: list[dict],
        route_policies_data: list[dict],
        dns_policies_data: list[dict],
        geo_policies_data: list[dict],
    ) -> dict:
        deleted = {
            "links": [],
            "dns_policies": [],
            "geo_policies": [],
            "route_policies": [],
            "balancers": [],
            "nodes": [],
        }
        if not replace:
            return deleted

        desired_node_names = {str(item["name"]) for item in nodes_data}
        desired_link_names = {str(item["name"]) for item in links_data}
        desired_balancer_refs = {(str(item["node_name"]), str(item["name"])) for item in balancers_data}
        desired_route_refs = {(str(item["node_name"]), str(item["name"])) for item in route_policies_data}
        desired_dns_refs = {
            (
                str((item.get("route_policy_ref") or {}).get("node_name") or ""),
                str((item.get("route_policy_ref") or {}).get("route_policy_name") or ""),
            )
            for item in dns_policies_data
        }
        desired_geo_refs = {
            (
                str((item.get("route_policy_ref") or {}).get("node_name") or ""),
                str((item.get("route_policy_ref") or {}).get("route_policy_name") or ""),
                str(item["country_code"]).strip().lower(),
            )
            for item in geo_policies_data
        }

        route_policy_name_by_id: dict[str, tuple[str, str]] = {}
        for policy in db.scalars(select(RoutePolicy)).all():
            node = db.get(Node, policy.node_id)
            if node is not None:
                route_policy_name_by_id[policy.id] = (node.name, policy.name)

        for policy in list(db.scalars(select(DNSPolicy)).all()):
            route_ref = route_policy_name_by_id.get(policy.route_policy_id)
            if route_ref not in desired_dns_refs:
                deleted["dns_policies"].append(f"{route_ref[0]}/{route_ref[1]}" if route_ref else policy.id)
                db.delete(policy)
        db.commit()

        for policy in list(db.scalars(select(GeoPolicy)).all()):
            route_ref = route_policy_name_by_id.get(policy.route_policy_id)
            key = (route_ref[0] if route_ref else "", route_ref[1] if route_ref else "", policy.country_code)
            if key not in desired_geo_refs:
                deleted["geo_policies"].append("/".join([key[0], key[1], key[2]]))
                db.delete(policy)
        db.commit()

        for policy in list(db.scalars(select(RoutePolicy)).all()):
            node = db.get(Node, policy.node_id)
            ref = (node.name if node else "", policy.name)
            if ref not in desired_route_refs:
                deleted["route_policies"].append(f"{ref[0]}/{ref[1]}")
                db.delete(policy)
        db.commit()

        for balancer in list(db.scalars(select(Balancer)).all()):
            node = db.get(Node, balancer.node_id)
            ref = (node.name if node else "", balancer.name)
            if ref not in desired_balancer_refs:
                deleted["balancers"].append(f"{ref[0]}/{ref[1]}")
                db.delete(balancer)
        db.commit()

        for link in list(db.scalars(select(Link)).all()):
            if link.name not in desired_link_names:
                deleted["links"].append(link.name)
                db.delete(link)
        db.commit()

        for node in list(db.scalars(select(Node)).all()):
            if node.name not in desired_node_names:
                deleted["nodes"].append(node.name)
                db.delete(node)
        db.commit()
        return deleted
