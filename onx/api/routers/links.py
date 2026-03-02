from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.link import Link
from onx.schemas.jobs import LinkApplyResponse
from onx.schemas.links import LinkCreate, LinkRead, LinkValidateResponse
from onx.services.link_service import LinkService


router = APIRouter(prefix="/links", tags=["links"])
link_service = LinkService()


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


@router.post("/{link_id}/apply", response_model=LinkApplyResponse)
def apply_link(link_id: str, db: Session = Depends(get_database_session)) -> LinkApplyResponse:
    link = db.get(Link, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    try:
        result = link_service.apply_link(db, link)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    applied_link = result["link"]
    return LinkApplyResponse(
        link_id=applied_link.id,
        state=applied_link.state.value if hasattr(applied_link.state, "value") else str(applied_link.state),
        message=result["message"],
        applied_at=datetime.now(timezone.utc),
    )
