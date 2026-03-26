from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from onx.compat import StrEnum
from onx.schemas.common import ONXBaseModel
from onx.schemas.jobs import JobRead
from onx.schemas.nodes import NodeAuthTypeValue


class QuickDeployScenarioValue(StrEnum):
    GATE_EGRESS = "gate_egress"


class QuickDeployStateValue(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuickDeployClientTransportValue(StrEnum):
    AWG = "awg"


class QuickDeployEgressTransportValue(StrEnum):
    XRAY_VLESS_XHTTP_REALITY = "xray_vless_xhttp_reality"


class QuickDeploySessionJobRead(ONXBaseModel):
    step: str
    job: JobRead


class QuickDeploySessionRead(ONXBaseModel):
    id: str
    scenario: QuickDeployScenarioValue
    state: QuickDeployStateValue
    current_stage: str | None
    request_payload_json: dict
    resources_json: dict
    child_jobs: list[QuickDeploySessionJobRead]
    error_text: str | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QuickDeploySessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: QuickDeployScenarioValue = QuickDeployScenarioValue.GATE_EGRESS
    gate_node_name: str | None = Field(default=None, min_length=1, max_length=128)
    gate_host: str = Field(min_length=1, max_length=255)
    gate_ssh_port: int = Field(default=22, ge=1, le=65535)
    gate_ssh_user: str = Field(default="root", min_length=1, max_length=64)
    gate_auth_type: NodeAuthTypeValue = NodeAuthTypeValue.PASSWORD
    gate_secret: str = Field(min_length=1)
    egress_node_name: str | None = Field(default=None, min_length=1, max_length=128)
    egress_host: str = Field(min_length=1, max_length=255)
    egress_ssh_port: int = Field(default=22, ge=1, le=65535)
    egress_ssh_user: str = Field(default="root", min_length=1, max_length=64)
    egress_auth_type: NodeAuthTypeValue = NodeAuthTypeValue.PASSWORD
    egress_secret: str = Field(min_length=1)
    gate_client_transport: QuickDeployClientTransportValue = QuickDeployClientTransportValue.AWG
    egress_transport: QuickDeployEgressTransportValue = QuickDeployEgressTransportValue.XRAY_VLESS_XHTTP_REALITY
    egress_server_name: str = Field(default="nos.nl", min_length=1, max_length=255)
    egress_xhttp_path: str = Field(default="/news", min_length=1, max_length=255)
    egress_listen_port: int = Field(default=443, ge=1, le=65535)
    gate_client_listen_port: int = Field(default=8443, ge=1, le=65535)
    gate_client_interface_name: str = Field(default="awg0", min_length=1, max_length=32)
    gate_client_server_address_v4: str = Field(default="10.250.0.1/24", min_length=1, max_length=64)
    transit_transparent_port: int = Field(default=15001, ge=1, le=65535)


class QuickDeploySessionCancelResult(ONXBaseModel):
    id: str
    state: QuickDeployStateValue
    message: str
