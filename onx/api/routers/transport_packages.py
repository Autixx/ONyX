import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

from onx.api.deps import get_database_session
from onx.db.models.transport_package import TransportPackage
from onx.db.models.user import User
from onx.schemas.transport_packages import (
    TransportPackageCreate,
    TransportPackageRead,
    TransportPackageReconcileResponse,
    TransportPackageUpdate,
    TransportPackageUpsert,
)
from onx.services.event_log_service import EventLogService
from onx.services.geoip_service import compute_excluded_allowed_ips
from onx.services.realtime_service import realtime_service
from onx.services.transport_package_service import transport_package_service


router = APIRouter(prefix="/transport-packages", tags=["transport-packages"])
event_log_service = EventLogService()


# ── Standalone template CRUD ──────────────────────────────────────────────────

@router.get("", response_model=list[TransportPackageRead], status_code=status.HTTP_200_OK)
def list_transport_packages(db: Session = Depends(get_database_session)):
    return transport_package_service.list_packages(db)


@router.post("", response_model=TransportPackageRead, status_code=status.HTTP_201_CREATED)
def create_transport_package(
    payload: TransportPackageCreate,
    db: Session = Depends(get_database_session),
) -> TransportPackage:
    pkg = TransportPackage(
        name=payload.name,
        enable_xray=payload.enable_xray,
        enable_awg=payload.enable_awg,
        enable_wg=payload.enable_wg,
        enable_openvpn_cloak=payload.enable_openvpn_cloak,
        split_tunnel_enabled=payload.split_tunnel_enabled,
        split_tunnel_routes_json=payload.split_tunnel_routes,
        priority_order_json=payload.priority_order,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.patch("/{package_id}", response_model=TransportPackageRead, status_code=status.HTTP_200_OK)
def update_transport_package(
    package_id: str,
    payload: TransportPackageUpdate,
    db: Session = Depends(get_database_session),
) -> TransportPackage:
    pkg = db.get(TransportPackage, package_id)
    if pkg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transport package not found.")
    dumped = payload.model_dump(exclude_unset=True)
    for field_name, value in dumped.items():
        if field_name == "split_tunnel_routes":
            pkg.split_tunnel_routes_json = value
        elif field_name == "priority_order":
            pkg.priority_order_json = value
        else:
            setattr(pkg, field_name, value)
    # If country code was set and split tunnel is enabled, auto-compute GeoIP routes
    if "split_tunnel_country_code" in dumped and pkg.split_tunnel_enabled and pkg.split_tunnel_country_code:
        try:
            pkg.split_tunnel_routes_json = compute_excluded_allowed_ips(pkg.split_tunnel_country_code.lower())
        except Exception:
            pass
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transport_package(
    package_id: str,
    db: Session = Depends(get_database_session),
) -> Response:
    pkg = db.get(TransportPackage, package_id)
    if pkg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transport package not found.")
    db.delete(pkg)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Per-user endpoints (backward-compatible) ──────────────────────────────────

@router.get("/by-user/{user_id}", response_model=TransportPackageRead, status_code=status.HTTP_200_OK)
def get_transport_package_for_user(user_id: str, db: Session = Depends(get_database_session)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return transport_package_service.get_or_create_for_user(db, user)


@router.put("/by-user/{user_id}", response_model=TransportPackageRead, status_code=status.HTTP_200_OK)
def upsert_transport_package_for_user(
    user_id: str,
    payload: TransportPackageUpsert,
    db: Session = Depends(get_database_session),
):
    try:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        package = transport_package_service.upsert_for_user(db, user, payload)
        event_log_service.log(
            db,
            entity_type="transport_package",
            entity_id=package.id,
            message=f"Transport package updated for user '{user.username}'.",
            details={"user_id": user.id, "enabled_transports": transport_package_service.enabled_transport_types(package)},
        )
        realtime_service.publish("transport_package.updated", {"id": package.id, "user_id": user.id})
        return package
    except HTTPException:
        raise
    except Exception as exc:
        _log.error("upsert_transport_package_for_user failed user_id=%s: %s", user_id, exc, exc_info=True)
        raise


@router.post("/by-user/{user_id}/reconcile", response_model=TransportPackageReconcileResponse, status_code=status.HTTP_200_OK)
def reconcile_transport_package_for_user(user_id: str, db: Session = Depends(get_database_session)):
    try:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        package = transport_package_service.get_or_create_for_user(db, user)
        summary = transport_package_service.reconcile_for_user(db, user, package)
        db.refresh(package)
        event_log_service.log(
            db,
            entity_type="transport_package",
            entity_id=package.id,
            message=f"Transport package reconciled for user '{user.username}'.",
            details=summary,
        )
        realtime_service.publish("transport_package.reconciled", {"id": package.id, "user_id": user.id})
        return TransportPackageReconcileResponse(package=TransportPackageRead.model_validate(package), summary=summary)
    except HTTPException:
        raise
    except Exception as exc:
        _log.error("reconcile_transport_package_for_user failed user_id=%s: %s", user_id, exc, exc_info=True)
        raise
