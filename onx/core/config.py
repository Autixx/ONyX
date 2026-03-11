import base64
import hashlib
import os
import socket
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ONX API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    debug: bool = False
    database_url: str = Field(
        default=f"sqlite:///{(Path(__file__).resolve().parents[2] / 'onx_dev.db').as_posix()}",
    )
    master_key: str = "onx-dev-master-key-change-me"
    ssh_connect_timeout_seconds: int = 10
    worker_poll_interval_seconds: int = 2
    worker_lease_seconds: int = 300
    probe_scheduler_enabled: bool = True
    probe_scheduler_interval_seconds: int = 30
    probe_scheduler_only_active_links: bool = True
    probe_ping_count: int = 3
    probe_ping_timeout_seconds: int = 1
    probe_load_sample_seconds: int = 1
    probe_load_reference_bytes_per_sec: float = 125000000.0
    client_session_ttl_seconds: int = 1800
    client_probe_interval_seconds: int = 15
    client_probe_fresh_seconds: int = 120
    client_probe_retention_seconds: int = 86400
    client_rebind_hysteresis_score: float = 15.0
    worker_id: str = Field(
        default_factory=lambda: f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}",
    )
    job_default_max_attempts: int = 3
    job_default_retry_delay_seconds: int = 15
    onx_conf_dir: str = "/etc/amnezia/amneziawg"
    onx_link_runner_path: str = "/usr/local/lib/onx/onx-link-runner"
    onx_link_unit_path: str = "/etc/systemd/system/onx-link@.service"
    onx_runtime_version: str = "1"

    model_config = SettingsConfigDict(
        env_prefix="ONX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_fernet_key() -> bytes:
    digest = hashlib.sha256(get_settings().master_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)
