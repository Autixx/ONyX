from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.job import JobKind, JobTargetType
from onx.db.models.link import Link
from onx.schemas.jobs import JobEnqueueOptions, JobRead
from onx.schemas.links import LinkCreate, LinkRead, LinkUpdate, LinkValidateResponse
from onx.services.job_service import JobConflictError, JobService
from onx.services.link_service import LinkService


router = APIRouter(prefix="/links", tags=["links"])
link_service = LinkService()
job_service = JobService()


@router.get("", response_model=list[LinkRead])
def list_links(db: Session = Depends(get_database_session)) -> list[Link]:
    return list(db.scalars(select(Link).order_by(Link.created_at.desc())).all())


@router.post("", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
def create_link(payload: LinkCreate, db: Session = Depends(get_database_session)) -> Link:
    try:
        return link_service.create_link(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{link_id}", response_model=LinkRead)
def get_link(link_id: str, db: Session = Depends(get_database_session)) -> Link:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    return link


@router.patch("/{link_id}", response_model=LinkRead)
def update_link(
    link_id: str,
    payload: LinkUpdate,
    db: Session = Depends(get_database_session),
) -> Link:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    try:
        return link_service.update_link(db, link, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(link_id: str, db: Session = Depends(get_database_session)) -> Response:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    try:
        link_service.delete_link(db, link)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{link_id}/validate", response_model=LinkValidateResponse)
def validate_link(link_id: str, db: Session = Depends(get_database_session)) -> LinkValidateResponse:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    try:
        result = link_service.validate_link(db, link)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return LinkValidateResponse(
        valid=result["valid"],
        warnings=result["warnings"],
        render_preview=result["render_preview"],
        capabilities=result["capabilities"],
    )


@router.post("/{link_id}/apply", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def apply_link(
    link_id: str,
    options: JobEnqueueOptions | None = Body(default=None),
    db: Session = Depends(get_database_session),
) -> JobRead:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")

    try:
        job = job_service.create_job(
            db,
            kind=JobKind.APPLY,
            target_type=JobTargetType.LINK,
            target_id=link.id,
            request_payload={
                "link_id": link.id,
                "link_name": link.name,
                "driver_name": link.driver_name,
            },
            max_attempts=options.max_attempts if options else None,
            retry_delay_seconds=options.retry_delay_seconds if options else None,
        )
    except JobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_job_id": exc.job_id,
                "existing_job_state": exc.job_state,
            },
        ) from exc
    return job
