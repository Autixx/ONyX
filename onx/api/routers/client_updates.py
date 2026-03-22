from fastapi import APIRouter, status

from onx.core.config import get_settings

router = APIRouter(tags=["client-updates"])


@router.get("/client/updates/latest", status_code=status.HTTP_200_OK)
def get_latest_update() -> dict:
    """Return the latest available client version info.

    Fields:
      - version:      latest version string (empty = no update published)
      - download_url: direct URL to the update ZIP archive
      - notes:        short release notes
    """
    settings = get_settings()
    return {
        "version": settings.client_latest_version,
        "download_url": settings.client_download_url,
        "notes": settings.client_update_notes,
    }
