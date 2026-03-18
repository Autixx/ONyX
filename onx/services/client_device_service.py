from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.device import Device, DeviceStatus
from onx.db.models.user import User
from onx.services.subscription_service import subscription_service


class ClientDeviceService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def list_for_user(self, db: Session, *, user_id: str) -> list[Device]:
        return list(
            db.scalars(
                select(Device)
                .where(Device.user_id == user_id)
                .order_by(Device.created_at.desc())
            ).all()
        )

    def list_enriched(self, db: Session, *, user_id: str | None = None) -> list[dict]:
        query = select(Device).order_by(Device.created_at.desc())
        if user_id:
            query = query.where(Device.user_id == user_id)
        devices = list(db.scalars(query).all())
        user_ids = {device.user_id for device in devices}
        users = {
            user.id: user
            for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
        } if user_ids else {}
        return [self.serialize_device(device, user=users.get(device.user_id)) for device in devices]

    def serialize_device(self, device: Device, *, user: User | None = None) -> dict:
        metadata = dict(device.metadata_json or {})
        return {
            "id": device.id,
            "user_id": device.user_id,
            "user_username": user.username if user is not None else None,
            "device_public_key": device.device_public_key,
            "device_label": device.device_label,
            "platform": device.platform,
            "app_version": device.app_version,
            "os_version": self._device_os_version(metadata),
            "timezone_gmt": self._device_timezone_gmt(metadata),
            "status": device.status,
            "metadata_json": metadata,
            "verified_at": device.verified_at,
            "first_seen_at": device.first_seen_at,
            "last_seen_at": device.last_seen_at,
            "banned_at": device.banned_at,
            "banned_until": device.banned_until,
            "ban_reason": device.ban_reason,
            "revoked_at": device.revoked_at,
            "created_at": device.created_at,
            "updated_at": device.updated_at,
        }

    def get_owned_device(self, db: Session, *, user_id: str, device_id: str) -> Device:
        device = db.get(Device, device_id)
        if device is None or device.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
        return device

    def register_device(
        self,
        db: Session,
        *,
        user: User,
        device_public_key: str,
        device_label: str | None,
        platform: str | None,
        app_version: str | None,
        metadata: dict,
    ) -> tuple[Device, int, int]:
        tz_offset_minutes = self.extract_timezone_offset_minutes(metadata or {})
        subscription = subscription_service.get_active_for_user(
            db,
            user_id=user.id,
            tz_offset_minutes=tz_offset_minutes,
        )
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active subscription for device registration.")
        device_limit = int(subscription.device_limit)
        normalized_key = device_public_key.strip()
        self._parse_public_key(normalized_key)
        existing = db.scalar(select(Device).where(Device.device_public_key == normalized_key))
        if existing is not None:
            if existing.status == DeviceStatus.REVOKED:
                db.delete(existing)
                db.commit()
                existing = None
            elif self._is_ban_expired(existing):
                existing.status = DeviceStatus.ACTIVE if existing.verified_at else DeviceStatus.PENDING
                existing.banned_at = None
                existing.banned_until = None
                existing.ban_reason = None
                db.add(existing)
                db.commit()
                db.refresh(existing)
            elif existing.status == DeviceStatus.BANNED:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=self._ban_detail(existing))
        if existing is not None:
            if existing.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device public key already belongs to another user.")
            existing.device_label = device_label or existing.device_label
            existing.platform = platform or existing.platform
            existing.app_version = app_version or existing.app_version
            existing.metadata_json = metadata or existing.metadata_json
            existing.last_seen_at = datetime.now(timezone.utc)
            db.add(existing)
            db.commit()
            db.refresh(existing)
            active_count = self.active_device_count(db, user_id=user.id)
            return existing, device_limit, active_count

        active_count = self.active_device_count(db, user_id=user.id)
        if active_count >= device_limit:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device limit exceeded.")
        device = Device(
            user_id=user.id,
            device_public_key=normalized_key,
            device_label=device_label,
            platform=platform,
            app_version=app_version,
            status=DeviceStatus.PENDING,
            metadata_json=metadata or {},
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return device, device_limit, active_count + 1

    def issue_challenge(self, db: Session, *, device: Device) -> tuple[str, datetime, dict]:
        plaintext = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._settings.client_device_challenge_ttl_seconds)
        device.challenge_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        device.challenge_expires_at = expires_at
        device.last_seen_at = datetime.now(timezone.utc)
        db.add(device)
        db.commit()
        envelope = self.encrypt_for_public_key(
            device.device_public_key,
            {
                "challenge": plaintext,
                "device_id": device.id,
                "expires_at": expires_at.isoformat(),
            },
        )
        return plaintext, expires_at, envelope

    def verify_challenge(self, db: Session, *, device: Device, challenge_response: str) -> Device:
        now = datetime.now(timezone.utc)
        if not device.challenge_hash or device.challenge_expires_at is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active device challenge.")
        if device.challenge_expires_at <= now:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device challenge expired.")
        if hashlib.sha256(challenge_response.encode("utf-8")).hexdigest() != device.challenge_hash:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device challenge response is invalid.")
        device.challenge_hash = None
        device.challenge_expires_at = None
        device.verified_at = now
        device.status = DeviceStatus.ACTIVE
        device.last_seen_at = now
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    def assert_recently_verified(self, device: Device) -> None:
        if self._is_ban_expired(device):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device ban expired but the device must be re-registered.")
        if device.status == DeviceStatus.BANNED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=self._ban_detail(device))
        if device.status != DeviceStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device is not active.")
        if device.verified_at is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device is not verified.")
        max_age = timedelta(seconds=self._settings.client_device_verify_max_age_seconds)
        if datetime.now(timezone.utc) - device.verified_at > max_age:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device verification is stale.")

    def revoke_device(self, db: Session, *, device: Device) -> None:
        db.delete(device)
        db.commit()

    def ban_device(
        self,
        db: Session,
        *,
        device: Device,
        duration_minutes: int | None,
        permanent: bool,
        reason: str | None = None,
    ) -> Device:
        now = datetime.now(timezone.utc)
        device.status = DeviceStatus.BANNED
        device.banned_at = now
        device.banned_until = None if permanent else now + timedelta(minutes=max(1, int(duration_minutes or 0)))
        device.ban_reason = (reason or "").strip() or None
        device.challenge_hash = None
        device.challenge_expires_at = None
        device.revoked_at = None
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    def unban_device(self, db: Session, *, device: Device) -> Device:
        device.status = DeviceStatus.ACTIVE if device.verified_at is not None else DeviceStatus.PENDING
        device.banned_at = None
        device.banned_until = None
        device.ban_reason = None
        db.add(device)
        db.commit()
        db.refresh(device)
        return device

    def active_device_count(self, db: Session, *, user_id: str) -> int:
        rows = db.scalars(
            select(Device).where(Device.user_id == user_id, Device.status != DeviceStatus.REVOKED)
        ).all()
        return len(rows)

    @staticmethod
    def extract_timezone_offset_minutes(metadata: dict | None) -> int | None:
        if not metadata:
            return None
        for key in ("timezone_offset_minutes", "gmt_offset_minutes", "tz_offset_minutes"):
            value = metadata.get(key)
            if value is None or value == "":
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _is_ban_expired(device: Device) -> bool:
        return (
            device.status == DeviceStatus.BANNED
            and device.banned_until is not None
            and device.banned_until <= datetime.now(timezone.utc)
        )

    def _ban_detail(self, device: Device) -> str:
        if device.banned_until is None:
            return "Device is banned permanently."
        return f"Device is banned until {device.banned_until.isoformat()}."

    @staticmethod
    def _device_os_version(metadata: dict) -> str | None:
        for key in ("os_version", "os_release", "platform_version", "system_version"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    def _device_timezone_gmt(self, metadata: dict) -> str | None:
        offset = self.extract_timezone_offset_minutes(metadata)
        if offset is None:
            value = metadata.get("timezone_gmt") or metadata.get("timezone") or metadata.get("tz")
            return str(value) if value else None
        sign = "+" if offset >= 0 else "-"
        total = abs(int(offset))
        hours, minutes = divmod(total, 60)
        return f"GMT{sign}{hours:02d}:{minutes:02d}"

    @staticmethod
    def _parse_public_key(value: str) -> X25519PublicKey:
        try:
            raw = base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))
            return X25519PublicKey.from_public_bytes(raw)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid device public key.") from exc

    def encrypt_for_public_key(self, public_key_value: str, payload: dict) -> dict:
        recipient = self._parse_public_key(public_key_value)
        ephemeral = X25519PrivateKey.generate()
        shared = ephemeral.exchange(recipient)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"onyx-client-envelope-v1").derive(shared)
        nonce = secrets.token_bytes(12)
        cipher = ChaCha20Poly1305(key)
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        ephemeral_public = ephemeral.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {
            "alg": "x25519-chacha20poly1305",
            "ephemeral_public_key": base64.urlsafe_b64encode(ephemeral_public).decode("ascii").rstrip("="),
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii").rstrip("="),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii").rstrip("="),
        }


client_device_service = ClientDeviceService()
