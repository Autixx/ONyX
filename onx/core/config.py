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
    web_ui_enabled: bool = True
    web_ui_dir: str = "/opt/onyx/apps/web-admin/dist"
    database_url: str = Field(
        default=f"sqlite:///{(Path(__file__).resolve().parents[2] / 'onx_dev.db').as_posix()}",
    )
    master_key: str = "onx-dev-master-key-change-me"
    ssh_connect_timeout_seconds: int = 10
    worker_poll_interval_seconds: int = 2
    worker_lease_seconds: int = 300
    admin_api_auth_mode: str = "disabled"
    admin_api_tokens: str = ""
    admin_api_jwt_secret: str = ""
    admin_api_jwt_issuer: str = ""
    admin_api_jwt_audience: str = ""
    admin_api_jwt_leeway_seconds: int = 30
    admin_api_jwt_require_exp: bool = True
    admin_api_read_roles: str = "viewer,operator,admin"
    admin_api_write_roles: str = "operator,admin"
    admin_web_auth_enabled: bool = True
    admin_web_bootstrap_username: str = "admin"
    admin_web_bootstrap_password: str = ""
    admin_web_bootstrap_roles: str = "admin"
    admin_web_session_cookie_name: str = "onx_session"
    admin_web_session_ttl_seconds: int = 43200
    admin_web_secure_cookies: bool = True
    admin_web_cookie_same_site: str = "lax"
    admin_web_cookie_domain: str = ""
    admin_web_cookie_path: str = "/"
    admin_web_password_hash_iterations: int = 600000
    admin_web_session_touch_interval_seconds: int = 300
    admin_web_session_idle_timeout_seconds: int = 43200
    admin_web_ws_heartbeat_seconds: int = 20
    client_api_auth_mode: str = "disabled"
    client_api_tokens: str = ""
    client_api_jwt_secret: str = ""
    client_api_jwt_issuer: str = ""
    client_api_jwt_audience: str = ""
    client_api_jwt_leeway_seconds: int = 30
    client_api_jwt_require_exp: bool = True
    client_rate_limit_enabled: bool = True
    client_rate_limit_cleanup_interval_seconds: int = 300
    client_rl_bootstrap_ip_rate_per_minute: float = 10.0
    client_rl_bootstrap_ip_burst: int = 10
    client_rl_bootstrap_device_rate_per_minute: float = 5.0
    client_rl_bootstrap_device_burst: int = 5
    client_rl_common_ip_rate_per_minute: float = 300.0
    client_rl_common_ip_burst: int = 150
    client_rl_probe_session_rate_per_minute: float = 120.0
    client_rl_probe_session_burst: int = 60
    client_rl_best_session_rate_per_minute: float = 60.0
    client_rl_best_session_burst: int = 30
    client_rl_rebind_session_rate_per_minute: float = 20.0
    client_rl_rebind_session_burst: int = 10
    client_rl_rebind_cooldown_seconds: int = 5
    probe_scheduler_enabled: bool = True
    probe_scheduler_interval_seconds: int = 30
    probe_scheduler_only_active_links: bool = True
    retention_scheduler_enabled: bool = True
    retention_scheduler_interval_seconds: int = 3600
    probe_result_retention_seconds: int = 604800
    event_log_retention_seconds: int = 2592000
    probe_ping_count: int = 3
    probe_ping_timeout_seconds: int = 1
    probe_load_sample_seconds: int = 1
    probe_load_reference_bytes_per_sec: float = 125000000.0
    client_session_ttl_seconds: int = 1800
    client_auth_session_ttl_seconds: int = 2592000
    client_auth_session_idle_timeout_seconds: int = 2592000
    client_auth_session_touch_interval_seconds: int = 300
    client_device_challenge_ttl_seconds: int = 300
    client_device_verify_max_age_seconds: int = 86400
    client_bundle_ttl_seconds: int = 1800
    client_bundle_dns_resolver: str = "1.1.1.1"
    client_bundle_dns_force_all: bool = True
    client_bundle_dns_force_doh: bool = True
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
    onx_xray_conf_dir: str = "/etc/onyx/xray"
    onx_xray_unit_path: str = "/etc/systemd/system/onx-xray@.service"
    onx_openvpn_cloak_conf_dir: str = "/etc/onyx/openvpn-cloak"
    onx_openvpn_unit_path: str = "/etc/systemd/system/onx-openvpn@.service"
    onx_cloak_unit_path: str = "/etc/systemd/system/onx-cloak@.service"
    onx_transit_conf_dir: str = "/etc/onyx/transit"
    onx_transit_runner_path: str = "/usr/local/lib/onx/onx-transit-runner"
    onx_transit_unit_path: str = "/etc/systemd/system/onx-transit@.service"
    onx_public_base_url: str = ""
    onx_node_agent_path: str = "/usr/local/lib/onx/onx-node-agent"
    onx_node_agent_env_path: str = "/etc/onx/node-agent.env"
    onx_node_agent_service_path: str = "/etc/systemd/system/onx-node-agent.service"
    onx_node_agent_timer_path: str = "/etc/systemd/system/onx-node-agent.timer"
    onx_node_agent_version: str = "1"
    onx_node_agent_interval_seconds: int = 60
    onx_node_traffic_hard_enforcement_enabled: bool = True
    onx_node_traffic_guard_chain: str = "ONX_NODE_TRAFFIC_GUARD"
    onx_awg_tools_repo: str = "https://github.com/amnezia-vpn/amneziawg-tools.git"
    onx_awg_tools_ref: str = "master"
    onx_awg_go_repo: str = "https://github.com/amnezia-vpn/amneziawg-go.git"
    onx_awg_go_ref: str = "master"
    onx_go_bootstrap_version: str = "1.24.13"
    onx_cloak_version: str = "2.12.0"
    onx_cloak_release_base_url: str = "https://github.com/cbeuw/Cloak/releases/download"
    onx_xray_install_script_url: str = "https://github.com/XTLS/Xray-install/raw/main/install-release.sh"

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
