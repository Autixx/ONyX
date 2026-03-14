from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.schemas.common import ONXBaseModel


class BundleIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    destination_country_code: str | None = Field(default=None, min_length=2, max_length=8)
    candidate_limit: int = Field(default=4, ge=1, le=16)


class BundleRead(ONXBaseModel):
    id: str
    user_id: str
    device_id: str
    bundle_format_version: str
    bundle_hash: str
    expires_at: datetime
    invalidated_at: datetime | None
    created_at: datetime
    metadata_json: dict


class BundleIssueResponse(ONXBaseModel):
    bundle_id: str
    device_id: str
    bundle_format_version: str
    issued_at: datetime
    expires_at: datetime
    encrypted_bundle: dict
    bundle_hash: str
