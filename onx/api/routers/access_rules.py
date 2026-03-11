from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.api.security.admin_access import admin_access_control
from onx.schemas.access_rules import AccessRuleMatrixRead, AccessRuleRead, AccessRuleUpsert
from onx.services.access_rule_service import AccessRuleService


router = APIRouter(prefix="/access-rules", tags=["access-rules"])
access_rule_service = AccessRuleService()


@router.get("", response_model=list[AccessRuleRead])
def list_access_rules(db: Session = Depends(get_database_session)) -> list[dict]:
    return [
        {
            "id": item.id,
            "permission_key": item.permission_key,
            "description": item.description,
            "allowed_roles": list(item.allowed_roles_json or []),
            "enabled": item.enabled,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in access_rule_service.list_rules(db)
    ]


@router.get("/matrix", response_model=AccessRuleMatrixRead)
def get_access_rule_matrix(db: Session = Depends(get_database_session)) -> AccessRuleMatrixRead:
    return AccessRuleMatrixRead(
        items=admin_access_control.describe_permission_matrix(db)
    )


@router.put("/{permission_key}", response_model=AccessRuleRead)
def upsert_access_rule(
    permission_key: str,
    payload: AccessRuleUpsert,
    db: Session = Depends(get_database_session),
) -> dict:
    try:
        rule = access_rule_service.upsert_rule(db, permission_key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "id": rule.id,
        "permission_key": rule.permission_key,
        "description": rule.description,
        "allowed_roles": list(rule.allowed_roles_json or []),
        "enabled": rule.enabled,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


@router.delete("/{permission_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_access_rule(permission_key: str, db: Session = Depends(get_database_session)) -> Response:
    rule = access_rule_service.get_rule_by_permission_key(db, permission_key)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access rule not found.")
    access_rule_service.delete_rule(db, rule)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
