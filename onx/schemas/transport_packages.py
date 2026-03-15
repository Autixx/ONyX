from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


SUPPORTED_TRANSPORT_TYPES = ("xray", "awg", "wg", "openvpn_cloak")
DEFAULT_TRANSPORT_PRIORITY = ["xray", "awg", "wg", "openvpn_cloak"]


class TransportPackageRead(ONXBaseModel):
    id: str
    user_id: str
    preferred_xray_service_id: str | None
    preferred_awg_service_id: str | None
    enable_xray: bool
    enable_awg: bool
    enable_wg: bool
    enable_openvpn_cloak: bool
    priority_order_json: list[str]
    last_reconciled_at: datetime | None
    last_reconcile_summary_json: dict | None
    created_at: datetime
    updated_at: datetime


class TransportPackageUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_xray_service_id: str | None = None
    preferred_awg_service_id: str | None = None
    enable_xray: bool = True
    enable_awg: bool = True
    enable_wg: bool = True
    enable_openvpn_cloak: bool = True
    priority_order: list[str] = Field(default_factory=lambda: list(DEFAULT_TRANSPORT_PRIORITY), min_length=1, max_length=8)


class TransportPackageReconcileResponse(ONXBaseModel):
    package: TransportPackageRead
    summary: dict
