from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from onx.core.config import get_settings
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.db.models.link import Link
from onx.db.models.node import Node
from onx.db.models.node_capability import NodeCapability
from onx.db.models.openvpn_cloak_service import OpenVpnCloakService
from onx.db.models.route_policy import RoutePolicy
from onx.db.models.transit_policy import TransitPolicy
from onx.db.models.awg_service import AwgService
from onx.db.models.wg_service import WgService
from onx.db.models.xray_service import XrayService
from onx.deploy.ssh_executor import SSHExecutor
from onx.db.session import SessionLocal
from onx.schemas.awg_services import AwgServiceRead
from onx.schemas.links import LinkRead
from onx.schemas.nodes import NodeCapabilityRead, serialize_node_read
from onx.schemas.openvpn_cloak_services import OpenVpnCloakServiceRead
from onx.schemas.route_policies import RoutePolicyRead
from onx.schemas.transit_policies import TransitPolicyRead
from onx.schemas.wg_services import WgServiceRead
from onx.schemas.xray_services import XrayServiceRead
from onx.services.awg_service_service import awg_service_manager
from onx.services.discovery_service import DiscoveryService
from onx.services.interface_runtime_service import InterfaceRuntimeService
from onx.services.job_service import JobCancelledError, JobService
from onx.services.link_service import LinkService
from onx.services.agh_install_service import AghInstallService
from onx.services.node_runtime_bootstrap_service import NodeRuntimeBootstrapService
from onx.services.openvpn_cloak_service_service import openvpn_cloak_service_manager
from onx.services.route_policy_service import RoutePolicyService
from onx.services.transit_policy_service import transit_policy_manager
from onx.services.wg_service_service import wg_service_manager
from onx.services.xray_service_service import xray_service_manager
from onx.workers.runtime_state import WorkerRuntimeState, get_worker_runtime_state


class JobWorker:
    def __init__(
        self,
        *,
        poll_interval_seconds: int = 2,
        lease_seconds: int = 300,
        worker_id: str | None = None,
        runtime_state: WorkerRuntimeState | None = None,
    ) -> None:
        settings = get_settings()
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._worker_id = worker_id or settings.worker_id
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._lock = Lock()
        self._jobs = JobService()
        self._discovery = DiscoveryService()
        self._links = LinkService()
        self._route_policies = RoutePolicyService()
        self._node_runtime = NodeRuntimeBootstrapService(InterfaceRuntimeService(SSHExecutor()))
        self._agh_install = AghInstallService()
        self._runtime_state = runtime_state or get_worker_runtime_state()

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._runtime_state.mark_started(
            worker_id=self._worker_id,
            poll_interval_seconds=self._poll_interval_seconds,
            lease_seconds=self._lease_seconds,
        )
        self._scheduler.add_job(
            self._poll_pending_jobs,
            "interval",
            seconds=self._poll_interval_seconds,
            id="onx-job-worker",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._runtime_state.mark_stopped()

    def _poll_pending_jobs(self) -> None:
        if not self._lock.acquire(blocking=False):
            return

        self._runtime_state.mark_poll_started()
        try:
            while True:
                with SessionLocal() as db:
                    job = self._jobs.acquire_next_job(
                        db,
                        worker_id=self._worker_id,
                        lease_seconds=self._lease_seconds,
                    )
                    if job is None:
                        break
                    self._runtime_state.mark_job_claimed()
                    self._execute_job(job.id)
        except Exception as exc:
            self._runtime_state.mark_error(str(exc))
            raise
        finally:
            self._runtime_state.mark_poll_finished()
            self._lock.release()

    def _execute_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if (
                job is None
                or job.state != JobState.RUNNING
                or job.worker_owner != self._worker_id
            ):
                return
            if job.cancel_requested:
                self._jobs.cancel(db, job, "Cancelled before execution start.")
                self._runtime_state.mark_job_cancelled()
                return

            try:
                if job.kind == JobKind.DISCOVER:
                    self._execute_discover(db, job)
                elif job.kind == JobKind.BOOTSTRAP:
                    self._execute_bootstrap(db, job)
                elif job.kind == JobKind.APPLY:
                    self._execute_apply(db, job)
                elif job.kind == JobKind.INSTALL_AGH:
                    self._execute_install_agh(db, job)
                else:
                    raise ValueError(f"Unsupported job kind '{job.kind.value}'.")
            except JobCancelledError:
                self._runtime_state.mark_job_cancelled()
                return
            except Exception as exc:
                db.rollback()
                current_job = db.get(Job, job_id)
                if current_job is not None:
                    self._jobs.handle_execution_error(db, current_job, str(exc))
                self._runtime_state.mark_error(str(exc))
            finally:
                db.rollback()
                final_job = db.get(Job, job_id)
                if final_job is not None:
                    if final_job.state == JobState.SUCCEEDED:
                        self._runtime_state.mark_job_succeeded()
                    elif final_job.state in (JobState.FAILED, JobState.DEAD):
                        self._runtime_state.mark_job_failed()
                    elif final_job.state == JobState.CANCELLED:
                        self._runtime_state.mark_job_cancelled()
                    elif final_job.state == JobState.PENDING and final_job.current_step == "retry scheduled":
                        self._runtime_state.mark_job_retried()

    def _execute_discover(self, db, job: Job) -> None:
        node = db.get(Node, job.target_id)
        if node is None:
            raise ValueError("Target node not found.")

        result = self._discovery.discover_node(
            db,
            node,
            progress_callback=lambda step: self._progress(db, job, step),
        )
        capabilities = list(
            db.scalars(
                select(NodeCapability)
                .where(NodeCapability.node_id == node.id)
                .order_by(NodeCapability.capability_name.asc())
            ).all()
        )
        db.refresh(node)
        self._jobs.succeed(
            db,
            job,
            {
                "node": serialize_node_read(node).model_dump(mode="json"),
                "interfaces": result["interfaces"],
                "capabilities": [
                    NodeCapabilityRead.model_validate(capability).model_dump(mode="json")
                    for capability in capabilities
                ],
            },
        )

    def _execute_apply(self, db, job: Job) -> None:
        if job.target_type == JobTargetType.LINK:
            link = db.get(Link, job.target_id)
            if link is None:
                raise ValueError("Target link not found.")

            result = self._links.apply_link(
                db,
                link,
                progress_callback=lambda step: self._progress(db, job, step),
            )
            applied_link = result["link"]
            self._jobs.succeed(
                db,
                job,
                {
                    "link": LinkRead.model_validate(applied_link).model_dump(mode="json"),
                    "message": result["message"],
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        if job.target_type == JobTargetType.AWG_SERVICE:
            service = db.get(AwgService, job.target_id)
            if service is None:
                raise ValueError("Target AWG service not found.")
            result = awg_service_manager.apply_service(db, service)
            self._jobs.succeed(
                db,
                job,
                {
                    "service": AwgServiceRead.model_validate(result["service"]).model_dump(mode="json"),
                    "peer_count": result["peer_count"],
                    "config_path": result["config_path"],
                },
            )
            return

        if job.target_type == JobTargetType.WG_SERVICE:
            service = db.get(WgService, job.target_id)
            if service is None:
                raise ValueError("Target WG service not found.")
            result = wg_service_manager.apply_service(db, service)
            self._jobs.succeed(
                db,
                job,
                {
                    "service": WgServiceRead.model_validate(result["service"]).model_dump(mode="json"),
                    "peer_count": result["peer_count"],
                    "config_path": result["config_path"],
                },
            )
            return

        if job.target_type == JobTargetType.XRAY_SERVICE:
            service = db.get(XrayService, job.target_id)
            if service is None:
                raise ValueError("Target XRAY service not found.")
            result = xray_service_manager.apply_service(db, service)
            self._jobs.succeed(
                db,
                job,
                {
                    "service": XrayServiceRead.model_validate(result["service"]).model_dump(mode="json"),
                    "peer_count": result["peer_count"],
                    "config_path": result["config_path"],
                },
            )
            return

        if job.target_type == JobTargetType.OPENVPN_CLOAK_SERVICE:
            service = db.get(OpenVpnCloakService, job.target_id)
            if service is None:
                raise ValueError("Target OpenVPN+Cloak service not found.")
            result = openvpn_cloak_service_manager.apply_service(db, service)
            self._jobs.succeed(
                db,
                job,
                {
                    "service": OpenVpnCloakServiceRead.model_validate(result["service"]).model_dump(mode="json"),
                    "peer_count": result["peer_count"],
                    "config_path": result["config_path"],
                },
            )
            return

        if job.target_type == JobTargetType.TRANSIT_POLICY:
            policy = db.get(TransitPolicy, job.target_id)
            if policy is None:
                raise ValueError("Target transit policy not found.")
            result = transit_policy_manager.apply_policy(db, policy)
            self._jobs.succeed(
                db,
                job,
                {
                    "policy": TransitPolicyRead.model_validate(result["policy"]).model_dump(mode="json"),
                    "config_path": result["config_path"],
                    "chain_name": result["chain_name"],
                },
            )
            return

        if job.target_type == JobTargetType.POLICY:
            policy = db.get(RoutePolicy, job.target_id)
            if policy is None:
                raise ValueError("Target route policy not found.")

            request_payload = job.request_payload_json or {}
            execution_mode = str(request_payload.get("execution_mode") or "live")
            if execution_mode == "planned":
                planned_plan = request_payload.get("plan")
                if not isinstance(planned_plan, dict):
                    raise ValueError("Planned execution mode requires 'plan' payload.")
                result = self._route_policies.apply_planned_policy(
                    db,
                    policy,
                    planned=planned_plan,
                    enforce_snapshot=bool(request_payload.get("enforce_snapshot", True)),
                    progress_callback=lambda step: self._progress(db, job, step),
                )
            else:
                result = self._route_policies.apply_policy(
                    db,
                    policy,
                    progress_callback=lambda step: self._progress(db, job, step),
                )
            applied_policy = result["policy"]
            self._jobs.succeed(
                db,
                job,
                {
                    "policy": RoutePolicyRead.model_validate(applied_policy).model_dump(mode="json"),
                    "message": result["message"],
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        raise ValueError(f"Unsupported apply target type '{job.target_type.value}'.")

    def _execute_install_agh(self, db, job: Job) -> None:
        node = db.get(Node, job.target_id)
        if node is None:
            raise ValueError("Target node not found.")

        result = self._agh_install.install_agh(
            db,
            node,
            progress_callback=lambda step: self._progress(db, job, step),
        )
        self._jobs.succeed(db, job, result)

    def _execute_bootstrap(self, db, job: Job) -> None:
        node = db.get(Node, job.target_id)
        if node is None:
            raise ValueError("Target node not found.")

        result = self._node_runtime.bootstrap_runtime(
            db,
            node,
            progress_callback=lambda step: self._progress(db, job, step),
        )
        self._jobs.succeed(db, job, result)

    def _progress(self, db, job: Job, step: str) -> None:
        self._jobs.heartbeat(
            db,
            job,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        self._jobs.update_step(db, job, step)
