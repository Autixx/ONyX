from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.db.models.user import User, UserStatus
from onx.schemas.users import UserCreate, UserRead, UserUpdate
from onx.services.admin_web_auth_service import admin_web_auth_service


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead], status_code=status.HTTP_200_OK)
def list_users(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_database_session),
) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if status_filter:
        query = query.where(User.status == UserStatus(status_filter.strip().lower()))
    if q:
        value = f"%{q.strip()}%"
        query = query.where((User.username.ilike(value)) | (User.email.ilike(value)))
    return list(db.scalars(query).all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_database_session)) -> User:
    existing = db.scalar(select(User).where((User.username == payload.username.strip()) | (User.email == payload.email.strip().lower())))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this username or email already exists.")
    user = User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        password_hash=admin_web_auth_service.hash_password(payload.password),
        status=payload.status,
        first_name=payload.first_name,
        last_name=payload.last_name,
        referral_code=payload.referral_code,
        usage_goal=payload.usage_goal,
        requested_device_count=payload.requested_device_count,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead, status_code=status.HTTP_200_OK)
def get_user(user_id: str, db: Session = Depends(get_database_session)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.patch("/{user_id}", response_model=UserRead, status_code=status.HTTP_200_OK)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_database_session)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "password":
            user.password_hash = admin_web_auth_service.hash_password(value)
            continue
        setattr(user, field_name, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_database_session)) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
