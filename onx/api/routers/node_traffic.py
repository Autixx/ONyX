from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.node import Node
from onx.schemas.node_traffic import (
    NodeTrafficActionRead,
    NodeTrafficCycleRead,
    NodeTrafficOverviewRead,
    NodeTrafficSummaryRead,
)
from onx.services.node_traffic_accounting_service import NodeTrafficAccountingService


router = APIRouter(prefix="/node-traffic", tags=["node-traffic"])
traffic_service = NodeTrafficAccountingService()


@router.get("/summary", response_model=list[NodeTrafficSummaryRead], status_code=status.HTTP_200_OK)
def list_node_traffic_summary(db: Session = Depends(get_database_session)) -> list[NodeTrafficSummaryRead]:
    nodes = list(db.scalars(select(Node).order_by(Node.name.asc())).all())
    usage_map = traffic_service.build_current_usage_gb_map(db)
    items: list[NodeTrafficSummaryRead] = []
    for node in nodes:
        cycle = traffic_service.find_current_cycle(db, node)
        usage_gb = usage_map.get(node.id, 0.0)
        ratio = round((usage_gb / float(node.traffic_limit_gb)), 4) if node.traffic_limit_gb and node.traffic_limit_gb > 0 else None
        items.append(
            NodeTrafficSummaryRead(
                node_id=node.id,
                node_name=node.name,
                node_status=node.status.value,
                traffic_limit_gb=node.traffic_limit_gb,
                traffic_used_gb=usage_gb,
                usage_ratio=ratio,
                cycle_started_at=cycle.cycle_started_at if cycle else None,
                cycle_ends_at=cycle.cycle_ends_at if cycle else None,
                traffic_suspended_at=node.traffic_suspended_at,
                traffic_suspension_reason=node.traffic_suspension_reason,
            )
        )
    return items


@router.get("/nodes/{node_id}", response_model=NodeTrafficOverviewRead, status_code=status.HTTP_200_OK)
def get_node_traffic_overview(node_id: str, limit: int = 12, db: Session = Depends(get_database_session)) -> NodeTrafficOverviewRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    recent_cycles = traffic_service.list_recent_cycles(db, node_id, limit=max(1, min(limit, 60)))
    current_cycle = traffic_service.get_current_cycle(db, node, create=True)
    db.commit()
    db.refresh(current_cycle)
    cycle_map = {cycle.id: cycle for cycle in recent_cycles}
    cycle_map[current_cycle.id] = current_cycle
    return NodeTrafficOverviewRead(
        node_id=node.id,
        node_name=node.name,
        traffic_suspended_at=node.traffic_suspended_at,
        traffic_suspension_reason=node.traffic_suspension_reason,
        current_cycle=NodeTrafficCycleRead.model_validate(traffic_service.serialize_cycle(node, current_cycle)),
        recent_cycles=[
            NodeTrafficCycleRead.model_validate(traffic_service.serialize_cycle(node, cycle))
            for cycle in sorted(cycle_map.values(), key=lambda item: item.cycle_started_at, reverse=True)[: max(1, min(limit, 60))]
        ],
    )


@router.post("/nodes/{node_id}/reset", response_model=NodeTrafficActionRead, status_code=status.HTTP_200_OK)
def reset_node_traffic(node_id: str, db: Session = Depends(get_database_session)) -> NodeTrafficActionRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    cycle = traffic_service.reset_current_cycle(db, node)
    db.refresh(node)
    return NodeTrafficActionRead(
        status="ok",
        node_id=node.id,
        node_name=node.name,
        action="reset",
        traffic_suspended_at=node.traffic_suspended_at,
        traffic_suspension_reason=node.traffic_suspension_reason,
        current_cycle=NodeTrafficCycleRead.model_validate(traffic_service.serialize_cycle(node, cycle)),
    )


@router.post("/nodes/{node_id}/rollover", response_model=NodeTrafficActionRead, status_code=status.HTTP_200_OK)
def rollover_node_traffic(node_id: str, db: Session = Depends(get_database_session)) -> NodeTrafficActionRead:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    cycle = traffic_service.rollover_cycle(db, node)
    db.refresh(node)
    return NodeTrafficActionRead(
        status="ok",
        node_id=node.id,
        node_name=node.name,
        action="rollover",
        traffic_suspended_at=node.traffic_suspended_at,
        traffic_suspension_reason=node.traffic_suspension_reason,
        current_cycle=NodeTrafficCycleRead.model_validate(traffic_service.serialize_cycle(node, cycle)),
    )
