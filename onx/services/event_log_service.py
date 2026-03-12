from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.db.models.event_log import EventLevel, EventLog
from onx.services.realtime_service import realtime_service


class EventLogService:
    def log(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str | None,
        message: str,
        level: EventLevel = EventLevel.INFO,
        job_id: str | None = None,
        details: dict | None = None,
    ) -> EventLog:
        event = EventLog(
            job_id=job_id,
            entity_type=entity_type,
            entity_id=entity_id,
            level=level,
            message=message,
            details_json=details,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        realtime_service.publish(
            "audit.event",
            {
                "id": event.id,
                "job_id": event.job_id,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "level": event.level.value,
                "message": event.message,
                "details_json": event.details_json,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            },
        )
        return event

    def list_events(
        self,
        db: Session,
        *,
        limit: int = 100,
        entity_type: str | None = None,
        entity_id: str | None = None,
        level: EventLevel | None = None,
    ) -> list[EventLog]:
        stmt = select(EventLog)
        if entity_type:
            stmt = stmt.where(EventLog.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(EventLog.entity_id == entity_id)
        if level is not None:
            stmt = stmt.where(EventLog.level == level)
        stmt = stmt.order_by(EventLog.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def list_for_job(self, db: Session, job_id: str) -> list[EventLog]:
        return list(
            db.scalars(
                select(EventLog)
                .where(EventLog.job_id == job_id)
                .order_by(EventLog.created_at.asc())
            ).all()
        )
