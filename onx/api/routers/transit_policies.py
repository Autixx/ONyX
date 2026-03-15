from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.event_log import EventLevel
from onx.schemas.transit_policies import TransitPolicyCreate, TransitPolicyRead, TransitPolicyUpdate
from onx.services.event_log_service import EventLogService
from onx.services.realtime_service import realtime_service
from onx.services.transit_policy_service import transit_policy_manager


router = APIRouter(prefix="/transit-policies", tags=["transit-policies"])
event_log_service = EventLogService()


@router.get("", response_model=list[TransitPolicyRead], status_code=status.HTTP_200_OK)
def list_transit_policies(
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
):
    return transit_policy_manager.list_policies(db, node_id=node_id)


@router.post("", response_model=TransitPolicyRead, status_code=status.HTTP_201_CREATED)
def create_transit_policy(payload: TransitPolicyCreate, db: Session = Depends(get_database_session)):
    try:
        policy = transit_policy_manager.create_policy(db, payload)
        event_log_service.log(
            db,
            entity_type="transit_policy",
            entity_id=policy.id,
            message=f"Transit policy '{policy.name}' created.",
            details={"node_id": policy.node_id, "ingress_interface": policy.ingress_interface},
        )
        realtime_service.publish("transit_policy.created", {"id": policy.id, "name": policy.name, "node_id": policy.node_id})
        return policy
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{policy_id}", response_model=TransitPolicyRead, status_code=status.HTTP_200_OK)
def get_transit_policy(policy_id: str, db: Session = Depends(get_database_session)):
    policy = transit_policy_manager.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transit policy not found.")
    return policy


@router.patch("/{policy_id}", response_model=TransitPolicyRead, status_code=status.HTTP_200_OK)
def update_transit_policy(policy_id: str, payload: TransitPolicyUpdate, db: Session = Depends(get_database_session)):
    policy = transit_policy_manager.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transit policy not found.")
    try:
        updated = transit_policy_manager.update_policy(db, policy, payload)
        event_log_service.log(
            db,
            entity_type="transit_policy",
            entity_id=updated.id,
            message=f"Transit policy '{updated.name}' updated.",
            details={"node_id": updated.node_id, "state": updated.state.value},
        )
        realtime_service.publish("transit_policy.updated", {"id": updated.id, "name": updated.name, "node_id": updated.node_id})
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transit_policy(policy_id: str, db: Session = Depends(get_database_session)):
    policy = transit_policy_manager.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transit policy not found.")
    policy_name = policy.name
    policy_node_id = policy.node_id
    transit_policy_manager.delete_policy(db, policy)
    event_log_service.log(
        db,
        entity_type="transit_policy",
        entity_id=policy_id,
        message=f"Transit policy '{policy_name}' deleted.",
        details={"node_id": policy_node_id},
        level=EventLevel.WARNING,
    )
    realtime_service.publish("transit_policy.deleted", {"id": policy_id, "name": policy_name, "node_id": policy_node_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{policy_id}/apply", response_model=TransitPolicyRead, status_code=status.HTTP_200_OK)
def apply_transit_policy(policy_id: str, db: Session = Depends(get_database_session)):
    policy = transit_policy_manager.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transit policy not found.")
    try:
        result = transit_policy_manager.apply_policy(db, policy)
        event_log_service.log(
            db,
            entity_type="transit_policy",
            entity_id=policy.id,
            message=f"Transit policy '{policy.name}' applied.",
            details={
                "node_id": policy.node_id,
                "config_path": result["config_path"],
                "chain_name": result["chain_name"],
            },
        )
        realtime_service.publish(
            "transit_policy.applied",
            {
                "id": policy.id,
                "name": policy.name,
                "node_id": policy.node_id,
                "chain_name": result["chain_name"],
            },
        )
        return result["policy"]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
