from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.awg_service import AwgService
from onx.db.models.job import Job, JobKind, JobState, JobTargetType
from onx.db.models.node import Node, NodeAuthType, NodeRole
from onx.db.models.node_secret import NodeSecretKind
from onx.db.models.quick_deploy_session import QuickDeploySession
from onx.db.models.transit_policy import TransitPolicy
from onx.db.models.xray_service import XrayService
from onx.schemas.awg_services import AwgServiceCreate
from onx.schemas.jobs import JobRead
from onx.schemas.quick_deploy import (
    QuickDeployClientTransportValue,
    QuickDeployEgressTransportValue,
    QuickDeployScenarioValue,
    QuickDeploySessionCancelResult,
    QuickDeploySessionCreate,
    QuickDeploySessionJobRead,
    QuickDeploySessionRead,
    QuickDeployStateValue,
)
from onx.schemas.transit_policies import TransitPolicyCreate
from onx.schemas.xray_services import XrayServiceCreate
from onx.services.awg_service_service import awg_service_manager
from onx.services.event_log_service import EventLogService
from onx.services.job_service import JobConflictError, JobService
from onx.services.realtime_service import realtime_service
from onx.services.secret_service import SecretService
from onx.services.transit_policy_service import transit_policy_manager
from onx.services.xray_service_service import xray_service_manager


class QuickDeployManager:
    _NON_TERMINAL_JOB_STATES = {JobState.PENDING, JobState.RUNNING}

    def __init__(self) -> None:
        self._secrets = SecretService()
        self._jobs = JobService()
        self._events = EventLogService()

    def list_sessions(self, db: Session) -> list[QuickDeploySession]:
        return list(db.scalars(select(QuickDeploySession).order_by(QuickDeploySession.created_at.desc())).all())

    def get_session(self, db: Session, session_id: str) -> QuickDeploySession | None:
        return db.get(QuickDeploySession, session_id)

    def create_session(self, db: Session, payload: QuickDeploySessionCreate) -> QuickDeploySession:
        if payload.scenario != QuickDeployScenarioValue.GATE_EGRESS:
            raise ValueError("Only gate-egress quick deploy is supported in this build.")
        if payload.gate_client_transport != QuickDeployClientTransportValue.AWG:
            raise ValueError("Only AWG client transport is supported in this build.")
        if payload.egress_transport != QuickDeployEgressTransportValue.XRAY_VLESS_XHTTP_REALITY:
            raise ValueError("Only XRAY VLESS xHTTP REALITY egress is supported in this build.")

        gate_node = self._upsert_node_with_secret(
            db,
            name=self._resolve_node_name(payload.gate_node_name, "gate", payload.gate_host),
            role=NodeRole.GATEWAY,
            host=payload.gate_host,
            ssh_port=payload.gate_ssh_port,
            ssh_user=payload.gate_ssh_user,
            auth_type=NodeAuthType(payload.gate_auth_type.value),
            secret_value=payload.gate_secret,
        )
        egress_node = self._upsert_node_with_secret(
            db,
            name=self._resolve_node_name(payload.egress_node_name, "egress", payload.egress_host),
            role=NodeRole.EGRESS,
            host=payload.egress_host,
            ssh_port=payload.egress_ssh_port,
            ssh_user=payload.egress_ssh_user,
            auth_type=NodeAuthType(payload.egress_auth_type.value),
            secret_value=payload.egress_secret,
        )
        request_payload = payload.model_dump(exclude={"gate_secret", "egress_secret"}, mode="json")
        session = QuickDeploySession(
            scenario=payload.scenario.value,
            state=QuickDeployStateValue.PLANNED.value,
            current_stage="pending bootstrap",
            request_payload_json=request_payload,
            resources_json={
                "gate_node_id": gate_node.id,
                "egress_node_id": egress_node.id,
                "gate_node_name": gate_node.name,
                "egress_node_name": egress_node.name,
            },
            child_jobs_json=[],
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        self.publish_status(session, "quick_deploy.created")
        self._events.log(
            db,
            entity_type="quick_deploy",
            entity_id=session.id,
            message=f"Quick deploy session '{session.id}' created.",
            details={"scenario": session.scenario, "resources": session.resources_json},
        )
        return session

    def cancel_session(self, db: Session, session: QuickDeploySession) -> QuickDeploySessionCancelResult:
        if session.state in {QuickDeployStateValue.READY.value, QuickDeployStateValue.FAILED.value, QuickDeployStateValue.CANCELLED.value}:
            return QuickDeploySessionCancelResult(
                id=session.id,
                state=QuickDeployStateValue(session.state),
                message=f"Session is already {session.state}.",
            )

        current_job = self._current_child_job(db, session)
        if current_job is not None and current_job.state in self._NON_TERMINAL_JOB_STATES:
            try:
                self._jobs.request_cancel(db, current_job, "Cancelled by quick deploy session.")
            except Exception:
                pass

        session.state = QuickDeployStateValue.CANCELLED.value
        session.current_stage = "cancelled"
        session.finished_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        db.refresh(session)
        self.publish_status(session, "quick_deploy.cancelled")
        return QuickDeploySessionCancelResult(
            id=session.id,
            state=QuickDeployStateValue.CANCELLED,
            message="Quick deploy cancelled.",
        )

    def tick(self, db: Session, session: QuickDeploySession) -> QuickDeploySession:
        if session.state in {QuickDeployStateValue.READY.value, QuickDeployStateValue.FAILED.value, QuickDeployStateValue.CANCELLED.value}:
            return session

        session.state = QuickDeployStateValue.RUNNING.value
        db.add(session)
        db.commit()
        db.refresh(session)

        payload = dict(session.request_payload_json or {})
        resources = dict(session.resources_json or {})
        gate_node_id = str(resources["gate_node_id"])
        egress_node_id = str(resources["egress_node_id"])

        if self._advance_job_step(
            db,
            session,
            step="bootstrap_gate",
            kind=JobKind.BOOTSTRAP,
            target_type=JobTargetType.NODE,
            target_id=gate_node_id,
            request_payload={"node_id": gate_node_id, "node_name": resources.get("gate_node_name"), "bootstrap": "runtime_assets"},
        ) is None:
            return self.get_session(db, session.id) or session

        if self._advance_job_step(
            db,
            session,
            step="bootstrap_egress",
            kind=JobKind.BOOTSTRAP,
            target_type=JobTargetType.NODE,
            target_id=egress_node_id,
            request_payload={"node_id": egress_node_id, "node_name": resources.get("egress_node_name"), "bootstrap": "runtime_assets"},
        ) is None:
            return self.get_session(db, session.id) or session

        gate_awg_id = self._ensure_gate_awg_service(db, session, payload)
        if self._advance_job_step(
            db,
            session,
            step="apply_gate_awg",
            kind=JobKind.APPLY,
            target_type=JobTargetType.AWG_SERVICE,
            target_id=gate_awg_id,
            request_payload={"service_id": gate_awg_id},
        ) is None:
            return self.get_session(db, session.id) or session

        egress_xray_id = self._ensure_egress_xray_service(db, session, payload)
        if self._advance_job_step(
            db,
            session,
            step="apply_egress_xray",
            kind=JobKind.APPLY,
            target_type=JobTargetType.XRAY_SERVICE,
            target_id=egress_xray_id,
            request_payload={"service_id": egress_xray_id},
        ) is None:
            return self.get_session(db, session.id) or session

        gate_transit_xray_id = self._ensure_gate_transit_xray_service(db, session, payload)
        if self._advance_job_step(
            db,
            session,
            step="apply_gate_transit_xray",
            kind=JobKind.APPLY,
            target_type=JobTargetType.XRAY_SERVICE,
            target_id=gate_transit_xray_id,
            request_payload={"service_id": gate_transit_xray_id},
        ) is None:
            return self.get_session(db, session.id) or session

        transit_policy_id = self._ensure_transit_policy(db, session, payload)
        if self._advance_job_step(
            db,
            session,
            step="apply_transit_policy",
            kind=JobKind.APPLY,
            target_type=JobTargetType.TRANSIT_POLICY,
            target_id=transit_policy_id,
            request_payload={"policy_id": transit_policy_id},
        ) is None:
            return self.get_session(db, session.id) or session

        session = db.get(QuickDeploySession, session.id) or session
        session.state = QuickDeployStateValue.READY.value
        session.current_stage = "ready"
        session.error_text = None
        session.finished_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        db.refresh(session)
        self.publish_status(session, "quick_deploy.ready")
        self._events.log(
            db,
            entity_type="quick_deploy",
            entity_id=session.id,
            message="Quick deploy completed successfully.",
            details={"resources": session.resources_json},
        )
        return session

    def serialize(self, db: Session, session: QuickDeploySession) -> QuickDeploySessionRead:
        jobs: list[QuickDeploySessionJobRead] = []
        for entry in list(session.child_jobs_json or []):
            job_id = str(entry.get("job_id") or "").strip()
            if not job_id:
                continue
            job = db.get(Job, job_id)
            if job is None:
                continue
            jobs.append(QuickDeploySessionJobRead(step=str(entry.get("step") or ""), job=JobRead.model_validate(job)))
        return QuickDeploySessionRead(
            id=session.id,
            scenario=QuickDeployScenarioValue(session.scenario),
            state=QuickDeployStateValue(session.state),
            current_stage=session.current_stage,
            request_payload_json=dict(session.request_payload_json or {}),
            resources_json=dict(session.resources_json or {}),
            child_jobs=jobs,
            error_text=session.error_text,
            finished_at=session.finished_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _advance_job_step(
        self,
        db: Session,
        session: QuickDeploySession,
        *,
        step: str,
        kind: JobKind,
        target_type: JobTargetType,
        target_id: str,
        request_payload: dict,
    ) -> Job | None:
        session = db.get(QuickDeploySession, session.id) or session
        session.current_stage = step
        db.add(session)
        db.commit()
        db.refresh(session)

        entry = next((item for item in list(session.child_jobs_json or []) if item.get("step") == step), None)
        job: Job | None = None
        if entry is not None:
            job = db.get(Job, str(entry.get("job_id") or ""))
        if job is None:
            job = self._enqueue_or_reuse_job(
                db,
                kind=kind,
                target_type=target_type,
                target_id=target_id,
                request_payload=request_payload,
            )
            child_jobs = list(session.child_jobs_json or [])
            child_jobs.append({"step": step, "job_id": job.id})
            session.child_jobs_json = child_jobs
            db.add(session)
            db.commit()
            db.refresh(session)
            self.publish_status(session, "quick_deploy.progress")
            return None
        if job.state in self._NON_TERMINAL_JOB_STATES:
            return None
        if job.state != JobState.SUCCEEDED:
            session.state = QuickDeployStateValue.FAILED.value
            session.current_stage = step
            session.error_text = job.error_text or f"Job '{job.id}' ended in state '{job.state.value}'."
            session.finished_at = datetime.now(timezone.utc)
            db.add(session)
            db.commit()
            db.refresh(session)
            self.publish_status(session, "quick_deploy.failed")
            return None
        return job

    def _enqueue_or_reuse_job(
        self,
        db: Session,
        *,
        kind: JobKind,
        target_type: JobTargetType,
        target_id: str,
        request_payload: dict,
    ) -> Job:
        active_job = db.scalar(
            select(Job)
            .where(
                Job.target_type == target_type,
                Job.target_id == target_id,
                Job.state.in_([JobState.PENDING, JobState.RUNNING]),
            )
            .order_by(Job.created_at.asc())
        )
        if active_job is not None:
            if active_job.kind != kind:
                raise ValueError(
                    f"Conflicting active job '{active_job.id}' already exists for target {target_type.value}:{target_id}."
                )
            return active_job
        try:
            return self._jobs.create_job(
                db,
                kind=kind,
                target_type=target_type,
                target_id=target_id,
                request_payload=request_payload,
            )
        except JobConflictError as exc:
            job = db.get(Job, exc.job_id)
            if job is None:
                raise
            return job

    def _current_child_job(self, db: Session, session: QuickDeploySession) -> Job | None:
        for entry in reversed(list(session.child_jobs_json or [])):
            job_id = str(entry.get("job_id") or "").strip()
            if not job_id:
                continue
            job = db.get(Job, job_id)
            if job is not None:
                return job
        return None

    def _ensure_gate_awg_service(self, db: Session, session: QuickDeploySession, payload: dict) -> str:
        resources = dict(session.resources_json or {})
        service_id = str(resources.get("gate_awg_service_id") or "").strip()
        if service_id and db.get(AwgService, service_id) is not None:
            return service_id
        service = awg_service_manager.create_service(
            db,
            AwgServiceCreate(
                name=f"qd-{session.id[:8]}-gate-awg",
                node_id=str(resources["gate_node_id"]),
                interface_name=str(payload.get("gate_client_interface_name") or "awg0"),
                listen_port=int(payload.get("gate_client_listen_port") or 8443),
                public_host=str(payload.get("gate_host") or ""),
                public_port=int(payload.get("gate_client_listen_port") or 8443),
                server_address_v4=str(payload.get("gate_client_server_address_v4") or "10.250.0.1/24"),
            ),
        )
        resources["gate_awg_service_id"] = service.id
        resources["gate_awg_service_name"] = service.name
        session.resources_json = resources
        db.add(session)
        db.commit()
        return service.id

    def _ensure_egress_xray_service(self, db: Session, session: QuickDeploySession, payload: dict) -> str:
        resources = dict(session.resources_json or {})
        service_id = str(resources.get("egress_xray_service_id") or "").strip()
        if service_id and db.get(XrayService, service_id) is not None:
            return service_id
        listen_port = int(payload.get("egress_listen_port") or 443)
        service = xray_service_manager.create_service(
            db,
            XrayServiceCreate(
                name=f"qd-{session.id[:8]}-egress-xray",
                node_id=str(resources["egress_node_id"]),
                listen_host="0.0.0.0",
                listen_port=listen_port,
                public_host=str(payload.get("egress_host") or ""),
                public_port=listen_port,
                server_name=str(payload.get("egress_server_name") or "nos.nl"),
                xhttp_path=str(payload.get("egress_xhttp_path") or "/news"),
                tls_enabled=False,
                reality_enabled=True,
                reality_dest=f"{str(payload.get('egress_server_name') or 'nos.nl')}:443",
            ),
        )
        resources["egress_xray_service_id"] = service.id
        resources["egress_xray_service_name"] = service.name
        session.resources_json = resources
        db.add(session)
        db.commit()
        return service.id

    def _ensure_gate_transit_xray_service(self, db: Session, session: QuickDeploySession, payload: dict) -> str:
        resources = dict(session.resources_json or {})
        service_id = str(resources.get("gate_transit_xray_service_id") or "").strip()
        if service_id and db.get(XrayService, service_id) is not None:
            return service_id
        service = xray_service_manager.create_service(
            db,
            XrayServiceCreate(
                name=f"qd-{session.id[:8]}-gate-transit",
                node_id=str(resources["gate_node_id"]),
                listen_host="127.0.0.1",
                listen_port=18443,
                public_host=str(payload.get("gate_host") or ""),
                public_port=18443,
                server_name=None,
                xhttp_path="/gate",
                tls_enabled=False,
                reality_enabled=False,
            ),
        )
        resources["gate_transit_xray_service_id"] = service.id
        resources["gate_transit_xray_service_name"] = service.name
        session.resources_json = resources
        db.add(session)
        db.commit()
        return service.id

    def _ensure_transit_policy(self, db: Session, session: QuickDeploySession, payload: dict) -> str:
        resources = dict(session.resources_json or {})
        policy_id = str(resources.get("transit_policy_id") or "").strip()
        if policy_id and db.get(TransitPolicy, policy_id) is not None:
            return policy_id
        policy = transit_policy_manager.create_policy(
            db,
            TransitPolicyCreate(
                name=f"qd-{session.id[:8]}-gate-egress",
                node_id=str(resources["gate_node_id"]),
                ingress_interface=str(payload.get("gate_client_interface_name") or "awg0"),
                enabled=True,
                transparent_port=int(payload.get("transit_transparent_port") or 15001),
                ingress_service_kind="xray_service",
                ingress_service_ref_id=str(resources["gate_transit_xray_service_id"]),
                next_hop_kind="xray_service",
                next_hop_ref_id=str(resources["egress_xray_service_id"]),
                capture_protocols_json=["tcp", "udp"],
                capture_cidrs_json=["0.0.0.0/0"],
            ),
        )
        resources["transit_policy_id"] = policy.id
        resources["transit_policy_name"] = policy.name
        session.resources_json = resources
        db.add(session)
        db.commit()
        return policy.id

    def _upsert_node_with_secret(
        self,
        db: Session,
        *,
        name: str,
        role: NodeRole,
        host: str,
        ssh_port: int,
        ssh_user: str,
        auth_type: NodeAuthType,
        secret_value: str,
    ) -> Node:
        node = db.scalar(select(Node).where(Node.name == name))
        if node is None:
            node = Node(
                name=name,
                role=role,
                management_address=host,
                ssh_host=host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                auth_type=auth_type,
            )
            db.add(node)
            db.commit()
            db.refresh(node)
        else:
            node.role = role
            node.management_address = host
            node.ssh_host = host
            node.ssh_port = ssh_port
            node.ssh_user = ssh_user
            node.auth_type = auth_type
            db.add(node)
            db.commit()
            db.refresh(node)
        secret_kind = NodeSecretKind.SSH_PASSWORD if auth_type == NodeAuthType.PASSWORD else NodeSecretKind.SSH_PRIVATE_KEY
        self._secrets.upsert_node_secret(db, node.id, secret_kind, secret_value)
        db.commit()
        return node

    @staticmethod
    def _resolve_node_name(explicit_name: str | None, prefix: str, host: str) -> str:
        value = str(explicit_name or "").strip()
        if value:
            return value
        suffix = re.sub(r"[^a-zA-Z0-9]+", "-", host).strip("-").lower()[:80] or prefix
        return f"{prefix}-{suffix}"

    @staticmethod
    def publish_status(session: QuickDeploySession, event_name: str) -> None:
        realtime_service.publish(
            event_name,
            {
                "id": session.id,
                "scenario": session.scenario,
                "state": session.state,
                "current_stage": session.current_stage,
                "error_text": session.error_text,
                "finished_at": session.finished_at.isoformat() if session.finished_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            },
        )


quick_deploy_manager = QuickDeployManager()
