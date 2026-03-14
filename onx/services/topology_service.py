from __future__ import annotations

import heapq
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from onx.db.models.link import Link, LinkState
from onx.db.models.link_endpoint import LinkEndpoint, LinkSide
from onx.db.models.node import Node, NodeStatus
from onx.db.models.peer_traffic_state import PeerTrafficState
from onx.db.models.probe_result import ProbeResult, ProbeType
from onx.schemas.topology import PathPlanRequest


class TopologyService:
    def get_graph(self, db: Session) -> dict:
        nodes = list(db.scalars(select(Node).order_by(Node.name.asc())).all())
        links = list(db.scalars(select(Link).order_by(Link.created_at.desc())).all())
        endpoint_map = self._load_endpoint_map(db, [link.id for link in links])

        graph_nodes = []
        peer_count_rows = db.execute(
            select(
                PeerTrafficState.node_id,
                func.count(distinct(PeerTrafficState.peer_public_key)),
            ).group_by(PeerTrafficState.node_id)
        ).all()
        peer_count_map = {str(node_id): int(count) for node_id, count in peer_count_rows}
        for node in nodes:
            ping_probe = self._latest_probe(db, node_id=node.id, interface_name=None, probe_type=ProbeType.PING)
            load_probe = self._latest_probe(db, node_id=node.id, interface_name=None, probe_type=ProbeType.INTERFACE_LOAD)
            graph_nodes.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "role": node.role.value,
                    "status": node.status.value,
                    "management_address": node.management_address,
                    "last_seen_at": node.last_seen_at,
                    "traffic_suspended_at": node.traffic_suspended_at,
                    "traffic_suspension_reason": node.traffic_suspension_reason,
                    "metrics": {
                        "load_ratio": self._extract_load_ratio(load_probe),
                        "peer_count": peer_count_map.get(node.id, 0),
                        "ping_ms": self._extract_latency_ms(ping_probe),
                        "last_probe_at": self._probe_timestamp(ping_probe, load_probe),
                    },
                }
            )

        graph_edges = []
        for link in links:
            left_ep = endpoint_map.get((link.id, LinkSide.LEFT.value))
            right_ep = endpoint_map.get((link.id, LinkSide.RIGHT.value))
            metrics = self._estimate_link_metrics(
                db,
                left_node_id=link.left_node_id,
                right_node_id=link.right_node_id,
                left_interface=left_ep.interface_name if left_ep else None,
                right_interface=right_ep.interface_name if right_ep else None,
                latency_weight=1.0,
                load_weight=1.2,
                loss_weight=1.5,
            )
            graph_edges.append(
                {
                    "id": link.id,
                    "name": link.name,
                    "driver_name": link.driver_name,
                    "topology_type": link.topology_type.value,
                    "state": link.state.value,
                    "left_node_id": link.left_node_id,
                    "right_node_id": link.right_node_id,
                    "left_interface": left_ep.interface_name if left_ep else None,
                    "right_interface": right_ep.interface_name if right_ep else None,
                    "health": link.health_summary_json,
                    "metrics": metrics,
                }
            )

        return {
            "nodes": graph_nodes,
            "edges": graph_edges,
            "generated_at": datetime.now(timezone.utc),
        }

    def plan_path(self, db: Session, payload: PathPlanRequest) -> dict:
        source = db.get(Node, payload.source_node_id)
        destination = db.get(Node, payload.destination_node_id)
        if source is None:
            raise ValueError("Source node not found.")
        if destination is None:
            raise ValueError("Destination node not found.")
        if source.id == destination.id:
            raise ValueError("Source and destination nodes must be different.")

        avoid_nodes = set(payload.avoid_node_ids)
        if source.id in avoid_nodes or destination.id in avoid_nodes:
            raise ValueError("Source/destination cannot be part of avoid_node_ids.")

        links_query = select(Link)
        if payload.require_active_links:
            links_query = links_query.where(Link.state == LinkState.ACTIVE)
        else:
            links_query = links_query.where(Link.state != LinkState.DELETED)
        links = list(db.scalars(links_query).all())
        if not links:
            raise ValueError("No links available for path planning.")

        endpoint_map = self._load_endpoint_map(db, [link.id for link in links])
        nodes_map = {node.id: node for node in db.scalars(select(Node)).all()}
        adjacency: dict[str, list[dict[str, Any]]] = {}

        for link in links:
            left_node = nodes_map.get(link.left_node_id)
            right_node = nodes_map.get(link.right_node_id)
            if left_node is None or right_node is None:
                continue
            if left_node.id in avoid_nodes or right_node.id in avoid_nodes:
                continue
            if left_node.status == NodeStatus.OFFLINE or right_node.status == NodeStatus.OFFLINE:
                continue
            if left_node.traffic_suspended_at is not None or right_node.traffic_suspended_at is not None:
                continue

            left_ep = endpoint_map.get((link.id, LinkSide.LEFT.value))
            right_ep = endpoint_map.get((link.id, LinkSide.RIGHT.value))
            metrics = self._estimate_link_metrics(
                db,
                left_node_id=link.left_node_id,
                right_node_id=link.right_node_id,
                left_interface=left_ep.interface_name if left_ep else None,
                right_interface=right_ep.interface_name if right_ep else None,
                latency_weight=payload.latency_weight,
                load_weight=payload.load_weight,
                loss_weight=payload.loss_weight,
            )

            self._add_edge(
                adjacency,
                from_node_id=link.left_node_id,
                to_node_id=link.right_node_id,
                link=link,
                from_interface=left_ep.interface_name if left_ep else None,
                to_interface=right_ep.interface_name if right_ep else None,
                metrics=metrics,
            )
            self._add_edge(
                adjacency,
                from_node_id=link.right_node_id,
                to_node_id=link.left_node_id,
                link=link,
                from_interface=right_ep.interface_name if right_ep else None,
                to_interface=left_ep.interface_name if left_ep else None,
                metrics=metrics,
            )

        if source.id not in adjacency:
            raise ValueError("Source node has no reachable outgoing links.")

        result = self._dijkstra(
            adjacency=adjacency,
            source_node_id=source.id,
            destination_node_id=destination.id,
            max_hops=payload.max_hops,
        )
        if result is None:
            raise ValueError("No path found with current constraints.")

        return {
            "source_node_id": source.id,
            "destination_node_id": destination.id,
            "node_path": result["node_path"],
            "hops": result["hops"],
            "total_score": round(result["total_score"], 3),
            "explored_states": result["explored_states"],
            "generated_at": datetime.now(timezone.utc),
        }

    def _dijkstra(
        self,
        *,
        adjacency: dict[str, list[dict[str, Any]]],
        source_node_id: str,
        destination_node_id: str,
        max_hops: int,
    ) -> dict | None:
        heap: list[tuple[float, int, str, list[str], list[dict[str, Any]]]] = []
        heapq.heappush(heap, (0.0, 0, source_node_id, [source_node_id], []))
        best_cost: dict[tuple[str, int], float] = {(source_node_id, 0): 0.0}
        explored_states = 0

        while heap:
            total_score, hops_used, current, node_path, hop_path = heapq.heappop(heap)
            explored_states += 1

            if current == destination_node_id:
                return {
                    "node_path": node_path,
                    "hops": hop_path,
                    "total_score": total_score,
                    "explored_states": explored_states,
                }

            if hops_used >= max_hops:
                continue

            for edge in adjacency.get(current, []):
                next_node = edge["to_node_id"]
                if next_node in node_path:
                    continue

                next_hops = hops_used + 1
                next_score = total_score + edge["metrics"]["score_hint"]
                state_key = (next_node, next_hops)
                if next_score >= best_cost.get(state_key, float("inf")):
                    continue
                best_cost[state_key] = next_score
                next_hop = {
                    "link_id": edge["link_id"],
                    "link_name": edge["link_name"],
                    "from_node_id": edge["from_node_id"],
                    "to_node_id": edge["to_node_id"],
                    "from_interface": edge["from_interface"],
                    "to_interface": edge["to_interface"],
                    "latency_ms": edge["metrics"]["latency_ms"],
                    "load_ratio": edge["metrics"]["load_ratio"],
                    "loss_pct": edge["metrics"]["loss_pct"],
                    "edge_score": edge["metrics"]["score_hint"],
                }
                heapq.heappush(
                    heap,
                    (
                        next_score,
                        next_hops,
                        next_node,
                        [*node_path, next_node],
                        [*hop_path, next_hop],
                    ),
                )

        return None

    @staticmethod
    def _add_edge(
        adjacency: dict[str, list[dict[str, Any]]],
        *,
        from_node_id: str,
        to_node_id: str,
        link: Link,
        from_interface: str | None,
        to_interface: str | None,
        metrics: dict,
    ) -> None:
        edge = {
            "link_id": link.id,
            "link_name": link.name,
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "from_interface": from_interface,
            "to_interface": to_interface,
            "metrics": metrics,
        }
        adjacency.setdefault(from_node_id, []).append(edge)

    @staticmethod
    def _load_endpoint_map(db: Session, link_ids: list[str]) -> dict[tuple[str, str], LinkEndpoint]:
        if not link_ids:
            return {}
        rows = list(
            db.scalars(select(LinkEndpoint).where(LinkEndpoint.link_id.in_(link_ids))).all()
        )
        return {(row.link_id, row.side.value): row for row in rows}

    def _estimate_link_metrics(
        self,
        db: Session,
        *,
        left_node_id: str,
        right_node_id: str,
        left_interface: str | None,
        right_interface: str | None,
        latency_weight: float,
        load_weight: float,
        loss_weight: float,
    ) -> dict:
        left_ping = self._latest_probe(db, left_node_id, left_interface, ProbeType.PING)
        right_ping = self._latest_probe(db, right_node_id, right_interface, ProbeType.PING)
        left_load = self._latest_probe(db, left_node_id, left_interface, ProbeType.INTERFACE_LOAD)
        right_load = self._latest_probe(db, right_node_id, right_interface, ProbeType.INTERFACE_LOAD)

        latency_values = [
            value
            for value in (
                self._extract_latency_ms(left_ping),
                self._extract_latency_ms(right_ping),
            )
            if value is not None
        ]
        loss_values = [
            value
            for value in (
                self._extract_loss_pct(left_ping),
                self._extract_loss_pct(right_ping),
            )
            if value is not None
        ]
        load_values = [
            value
            for value in (
                self._extract_load_ratio(left_load),
                self._extract_load_ratio(right_load),
            )
            if value is not None
        ]

        latency_ms = round(sum(latency_values) / len(latency_values), 3) if latency_values else 120.0
        loss_pct = round(sum(loss_values) / len(loss_values), 3) if loss_values else 0.5
        load_ratio = round(sum(load_values) / len(load_values), 4) if load_values else 0.2

        score = (
            1.0
            + latency_weight * (latency_ms / 100.0)
            + load_weight * (load_ratio * 5.0)
            + loss_weight * (loss_pct / 10.0)
        )
        return {
            "latency_ms": round(latency_ms, 3),
            "load_ratio": round(load_ratio, 4),
            "loss_pct": round(loss_pct, 3),
            "score_hint": round(score, 3),
        }

    @staticmethod
    def _latest_probe(
        db: Session,
        node_id: str,
        interface_name: str | None,
        probe_type: ProbeType,
    ) -> ProbeResult | None:
        if interface_name:
            exact = db.scalar(
                select(ProbeResult)
                .where(
                    ProbeResult.source_node_id == node_id,
                    ProbeResult.probe_type == probe_type,
                    ProbeResult.member_interface == interface_name,
                )
                .order_by(ProbeResult.created_at.desc())
                .limit(1)
            )
            if exact is not None:
                return exact
        return db.scalar(
            select(ProbeResult)
            .where(
                ProbeResult.source_node_id == node_id,
                ProbeResult.probe_type == probe_type,
            )
            .order_by(ProbeResult.created_at.desc())
            .limit(1)
        )

    @staticmethod
    def _extract_latency_ms(probe: ProbeResult | None) -> float | None:
        if probe is None:
            return None
        metrics = probe.metrics_json or {}
        return TopologyService._metric_float(metrics, ("latency_ms", "rtt_ms", "value"))

    @staticmethod
    def _extract_loss_pct(probe: ProbeResult | None) -> float | None:
        if probe is None:
            return None
        metrics = probe.metrics_json or {}
        return TopologyService._metric_float(metrics, ("loss_pct", "packet_loss", "loss"))

    @staticmethod
    def _extract_load_ratio(probe: ProbeResult | None) -> float | None:
        if probe is None:
            return None
        metrics = probe.metrics_json or {}
        value = TopologyService._metric_float(metrics, ("load_ratio", "value", "load"))
        if value is None:
            return None
        if value > 1.0:
            value = value / 100.0
        if value < 0.0:
            value = 0.0
        if value > 1.0:
            value = 1.0
        return value

    @staticmethod
    def _metric_float(metrics: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            raw = metrics.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _probe_timestamp(*probes: ProbeResult | None) -> datetime | None:
        timestamps = [probe.created_at for probe in probes if probe is not None and probe.created_at is not None]
        if not timestamps:
            return None
        return max(timestamps)
