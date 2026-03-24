from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from onx.api.deps import get_database_session
from onx.core.config import get_settings
from onx.services.system_config_service import (
    SystemConfigService,
    CLIENT_UPDATE_FILENAME_KEY,
    CLIENT_UPDATE_MIRROR_URL_KEY,
    CLIENT_UPDATE_MODE_KEY,
    CLIENT_UPDATE_NOTES_KEY,
    CLIENT_UPDATE_VERSION_KEY,
)

router = APIRouter(tags=["client-updates"])
_svc = SystemConfigService()


# ── Schemas ─────────────────────────────────────────────────────────────────

class ClientUpdateConfigRead(BaseModel):
    mode: str         # "direct" | "mirror" | ""
    version: str
    notes: str
    mirror_url: str
    filename: str     # uploaded ZIP filename (direct mode only)
    download_url: str # resolved public URL for current config


class ClientUpdateConfigUpdate(BaseModel):
    mode: str | None = None
    version: str | None = None
    notes: str | None = None
    mirror_url: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_config(db: Session) -> ClientUpdateConfigRead:
    settings = get_settings()
    mode       = _svc.get(db, CLIENT_UPDATE_MODE_KEY) or ""
    version    = _svc.get(db, CLIENT_UPDATE_VERSION_KEY) or ""
    notes      = _svc.get(db, CLIENT_UPDATE_NOTES_KEY) or ""
    mirror_url = _svc.get(db, CLIENT_UPDATE_MIRROR_URL_KEY) or ""
    filename   = _svc.get(db, CLIENT_UPDATE_FILENAME_KEY) or ""

    if mode == "mirror":
        url = mirror_url
    elif mode == "direct":
        public_base = (_svc.get_public_base_url(db) or "").rstrip("/")
        url = f"{public_base}/client-updates/{filename}" if filename and public_base else ""
    else:
        url = ""

    return ClientUpdateConfigRead(
        mode=mode, version=version, notes=notes,
        mirror_url=mirror_url, filename=filename, download_url=url,
    )


# ── Public client endpoint ───────────────────────────────────────────────────

@router.get("/client/updates/latest", status_code=status.HTTP_200_OK)
def get_latest_update(db: Session = Depends(get_database_session)) -> dict:
    """Return the latest available client version info."""
    settings = get_settings()
    cfg = _resolve_config(db)
    # Fall back to env-var values if DB has nothing configured.
    version = cfg.version or settings.client_latest_version
    if not version:
        return {"version": "", "download_url": "", "notes": ""}
    notes = cfg.notes or settings.client_update_notes
    url   = cfg.download_url or settings.client_download_url
    return {"version": version, "download_url": url, "notes": notes}


# ── Admin config endpoints ───────────────────────────────────────────────────

@router.get("/admin/client-updates/config", status_code=status.HTTP_200_OK)
def get_client_update_config(db: Session = Depends(get_database_session)) -> ClientUpdateConfigRead:
    return _resolve_config(db)


@router.patch("/admin/client-updates/config", status_code=status.HTTP_200_OK)
def update_client_update_config(
    body: ClientUpdateConfigUpdate,
    db: Session = Depends(get_database_session),
) -> ClientUpdateConfigRead:
    if body.mode is not None:
        _svc.set(db, CLIENT_UPDATE_MODE_KEY, body.mode.strip())
    if body.version is not None:
        _svc.set(db, CLIENT_UPDATE_VERSION_KEY, body.version.strip())
    if body.notes is not None:
        _svc.set(db, CLIENT_UPDATE_NOTES_KEY, body.notes.strip())
    if body.mirror_url is not None:
        _svc.set(db, CLIENT_UPDATE_MIRROR_URL_KEY, body.mirror_url.strip())
    return _resolve_config(db)


@router.post("/admin/client-updates/upload", status_code=status.HTTP_200_OK)
async def upload_client_update(
    version: str = Query(...),
    notes: str = Query(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_database_session),
) -> ClientUpdateConfigRead:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")
    version = version.strip()
    if not version:
        raise HTTPException(status_code=400, detail="version query param is required.")
    settings = get_settings()
    updates_dir = Path(settings.client_updates_dir).expanduser().resolve()
    updates_dir.mkdir(parents=True, exist_ok=True)
    safe_version = version.replace(" ", "_").replace("/", "_").replace("..", "_")
    filename = f"ONyXClient-{safe_version}.zip"
    dest = updates_dir / filename
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    _svc.set(db, CLIENT_UPDATE_MODE_KEY, "direct")
    _svc.set(db, CLIENT_UPDATE_VERSION_KEY, version)
    _svc.set(db, CLIENT_UPDATE_NOTES_KEY, notes.strip())
    _svc.set(db, CLIENT_UPDATE_FILENAME_KEY, filename)
    return _resolve_config(db)
