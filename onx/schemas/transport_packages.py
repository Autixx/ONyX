from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


SUPPORTED_TRANSPORT_TYPES = ("xray", "awg", "wg", "openvpn_cloak")
DEFAULT_TRANSPORT_PRIORITY = ["xray", "awg", "wg", "openvpn_cloak"]


class TransportPackageRead(ONXBaseModel):
    id: str
    name: str | None
    user_id: str | None
    preferred_xray_service_id: str | None
    preferred_awg_service_id: str | None
    preferred_wg_service_id: str | None
    preferred_openvpn_cloak_service_id: str | None
    enable_xray: bool
    enable_awg: bool
    enable_wg: bool
    enable_openvpn_cloak: bool
    split_tunnel_enabled: bool
    split_tunnel_country_code: str | None
    split_tunnel_routes_json: list[str]
    priority_order_json: list[str]
    last_reconciled_at: datetime | None
    last_reconcile_summary_json: dict | None
    created_at: datetime
    updated_at: datetime


class TransportPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    enable_xray: bool = True
    enable_awg: bool = True
    enable_wg: bool = True
    enable_openvpn_cloak: bool = True
    split_tunnel_enabled: bool = False
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TRANSPORT_PRIORITY),
        min_length=1,
        max_length=8,
    )


class TransportPackageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    enable_xray: bool | None = None
    enable_awg: bool | None = None
    enable_wg: bool | None = None
    enable_openvpn_cloak: bool | None = None
    split_tunnel_enabled: bool | None = None
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] | None = None
    priority_order: list[str] | None = Field(default=None, min_length=1, max_length=8)


class TransportPackageUpsert(BaseModel):
    """Used by the per-user upsert endpoint (backward-compatible)."""
    model_config = ConfigDict(extra="forbid")

    preferred_xray_service_id: str | None = None
    preferred_awg_service_id: str | None = None
    preferred_wg_service_id: str | None = None
    preferred_openvpn_cloak_service_id: str | None = None
    enable_xray: bool = True
    enable_awg: bool = True
    enable_wg: bool = True
    enable_openvpn_cloak: bool = True
    split_tunnel_enabled: bool = False
    split_tunnel_country_code: str | None = None
    split_tunnel_routes: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TRANSPORT_PRIORITY),
        min_length=1,
        max_length=8,
    )


class TransportPackageReconcileResponse(ONXBaseModel):
    package: TransportPackageRead
    summary: dict
