from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.services.system_config_service import SystemConfigService


router = APIRouter(prefix="/system/config", tags=["system-config"])
_svc = SystemConfigService()


class SystemConfigRead(BaseModel):
    public_base_url: str | None


class SystemConfigUpdate(BaseModel):
    public_base_url: str | None = None


@router.get("", response_model=SystemConfigRead)
def get_system_config(db: Session = Depends(get_database_session)) -> SystemConfigRead:
    return SystemConfigRead(public_base_url=_svc.get_public_base_url(db))


@router.patch("", response_model=SystemConfigRead)
def update_system_config(
    body: SystemConfigUpdate,
    db: Session = Depends(get_database_session),
) -> SystemConfigRead:
    if body.public_base_url is not None:
        _svc.set_public_base_url(db, body.public_base_url)
    return SystemConfigRead(public_base_url=_svc.get_public_base_url(db))
