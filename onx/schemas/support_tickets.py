from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class SupportTicketCreate(BaseModel):
    device_id: str | None = None
    issue_type: str
    message: str
    diagnostics: dict[str, Any] | None = None
    app_version: str | None = None
    platform: str | None = None

    @field_validator("issue_type")
    @classmethod
    def validate_issue_type(cls, v: str) -> str:
        allowed = {"connection", "speed", "billing", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"issue_type must be one of: {', '.join(sorted(allowed))}")
        return v.lower()

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        if len(v) > 4000:
            raise ValueError("message must not exceed 4000 characters")
        return v


class SupportTicketRead(BaseModel):
    id: str
    user_id: str
    device_id: str | None
    issue_type: str
    message: str
    diagnostics: dict[str, Any] | None
    app_version: str | None
    platform: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
