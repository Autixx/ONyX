from sqlalchemy.orm import Session

from onx.db.models.system_config import SystemConfig

PUBLIC_BASE_URL_KEY = "public_base_url"

CLIENT_UPDATE_MODE_KEY     = "client_update_mode"
CLIENT_UPDATE_VERSION_KEY  = "client_update_version"
CLIENT_UPDATE_NOTES_KEY    = "client_update_notes"
CLIENT_UPDATE_MIRROR_URL_KEY = "client_update_mirror_url"
CLIENT_UPDATE_FILENAME_KEY = "client_update_filename"


class SystemConfigService:
    def get(self, db: Session, key: str) -> str | None:
        row = db.get(SystemConfig, key)
        return row.value if row is not None else None

    def set(self, db: Session, key: str, value: str) -> None:
        row = db.get(SystemConfig, key)
        if row is None:
            row = SystemConfig(key=key, value=value)
        else:
            row.value = value
        db.add(row)
        db.commit()

    def get_public_base_url(self, db: Session) -> str | None:
        value = self.get(db, PUBLIC_BASE_URL_KEY)
        if not value:
            return None
        return value.strip().rstrip("/")

    def set_public_base_url(self, db: Session, url: str) -> None:
        self.set(db, PUBLIC_BASE_URL_KEY, url.strip().rstrip("/"))
