from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.schemas.quick_deploy import (
    QuickDeploySessionCancelResult,
    QuickDeploySessionCreate,
    QuickDeploySessionRead,
)
from onx.services.quick_deploy_service import quick_deploy_manager


router = APIRouter(prefix="/quick-deploy", tags=["quick-deploy"])


@router.get("/sessions", response_model=list[QuickDeploySessionRead], status_code=status.HTTP_200_OK)
def list_quick_deploy_sessions(db: Session = Depends(get_database_session)):
    return [quick_deploy_manager.serialize(db, item) for item in quick_deploy_manager.list_sessions(db)]


@router.post("/sessions", response_model=QuickDeploySessionRead, status_code=status.HTTP_201_CREATED)
def create_quick_deploy_session(payload: QuickDeploySessionCreate, db: Session = Depends(get_database_session)):
    try:
        session = quick_deploy_manager.create_session(db, payload)
        return quick_deploy_manager.serialize(db, session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=QuickDeploySessionRead, status_code=status.HTTP_200_OK)
def get_quick_deploy_session(session_id: str, db: Session = Depends(get_database_session)):
    session = quick_deploy_manager.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick deploy session not found.")
    return quick_deploy_manager.serialize(db, session)


@router.post("/sessions/{session_id}/cancel", response_model=QuickDeploySessionCancelResult, status_code=status.HTTP_200_OK)
def cancel_quick_deploy_session(session_id: str, db: Session = Depends(get_database_session)):
    session = quick_deploy_manager.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick deploy session not found.")
    return quick_deploy_manager.cancel_session(db, session)
