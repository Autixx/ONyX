from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_fernet_key
from onx.db.models.node_secret import NodeSecret, NodeSecretKind


class SecretService:
    def __init__(self) -> None:
        self._fernet = Fernet(get_fernet_key())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_value: str) -> str:
        return self._fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")

    def upsert_node_secret(self, db: Session, node_id: str, kind: NodeSecretKind, secret_value: str) -> NodeSecret:
        existing = db.scalar(
            select(NodeSecret).where(
                NodeSecret.node_id == node_id,
                NodeSecret.kind == kind,
                NodeSecret.is_active.is_(True),
            )
        )
        encrypted_value = self.encrypt(secret_value)
        if existing is None:
            secret = NodeSecret(
                node_id=node_id,
                kind=kind,
                secret_ref=f"node-secret:{node_id}:{kind}:{uuid4()}",
                encrypted_value=encrypted_value,
                is_active=True,
            )
            db.add(secret)
            db.flush()
            return secret

        existing.encrypted_value = encrypted_value
        existing.is_active = True
        db.add(existing)
        db.flush()
        return existing

    def upsert_node_secret_with_ref(
        self,
        db: Session,
        node_id: str,
        kind: NodeSecretKind,
        secret_ref: str,
        secret_value: str,
    ) -> NodeSecret:
        existing = db.scalar(select(NodeSecret).where(NodeSecret.secret_ref == secret_ref))
        encrypted_value = self.encrypt(secret_value)
        if existing is None:
            secret = NodeSecret(
                node_id=node_id,
                kind=kind,
                secret_ref=secret_ref,
                encrypted_value=encrypted_value,
                is_active=True,
            )
            db.add(secret)
            db.flush()
            return secret

        existing.node_id = node_id
        existing.kind = kind
        existing.encrypted_value = encrypted_value
        existing.is_active = True
        db.add(existing)
        db.flush()
        return existing

    def get_active_secret(self, db: Session, node_id: str, kind: NodeSecretKind) -> NodeSecret | None:
        return db.scalar(
            select(NodeSecret).where(
                NodeSecret.node_id == node_id,
                NodeSecret.kind == kind,
                NodeSecret.is_active.is_(True),
            )
        )

    def get_secret_by_ref(self, db: Session, secret_ref: str) -> NodeSecret | None:
        return db.scalar(select(NodeSecret).where(NodeSecret.secret_ref == secret_ref))
