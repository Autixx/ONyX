"""add devices and issued bundles

Revision ID: 0017_devices_and_bundles
Revises: 0016_client_identity
Create Date: 2026-03-15 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_devices_and_bundles"
down_revision: Union[str, Sequence[str], None] = "0016_client_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    device_status = sa.Enum("pending", "active", "revoked", name="device_status")

    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_public_key", sa.String(length=255), nullable=False),
        sa.Column("device_label", sa.String(length=128), nullable=True),
        sa.Column("platform", sa.String(length=64), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("status", device_status, nullable=False, server_default="pending"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=True),
        sa.Column("challenge_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)
    op.create_index(op.f("ix_devices_device_public_key"), "devices", ["device_public_key"], unique=True)

    op.create_table(
        "issued_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("bundle_format_version", sa.String(length=32), nullable=False, server_default="1"),
        sa.Column("bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_bundle_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_issued_bundles_user_id"), "issued_bundles", ["user_id"], unique=False)
    op.create_index(op.f("ix_issued_bundles_device_id"), "issued_bundles", ["device_id"], unique=False)
    op.create_index(op.f("ix_issued_bundles_bundle_hash"), "issued_bundles", ["bundle_hash"], unique=False)
    op.create_index(op.f("ix_issued_bundles_expires_at"), "issued_bundles", ["expires_at"], unique=False)


def downgrade() -> None:
    device_status = sa.Enum("pending", "active", "revoked", name="device_status")

    op.drop_index(op.f("ix_issued_bundles_expires_at"), table_name="issued_bundles")
    op.drop_index(op.f("ix_issued_bundles_bundle_hash"), table_name="issued_bundles")
    op.drop_index(op.f("ix_issued_bundles_device_id"), table_name="issued_bundles")
    op.drop_index(op.f("ix_issued_bundles_user_id"), table_name="issued_bundles")
    op.drop_table("issued_bundles")

    op.drop_index(op.f("ix_devices_device_public_key"), table_name="devices")
    op.drop_index(op.f("ix_devices_user_id"), table_name="devices")
    op.drop_table("devices")
    device_status.drop(op.get_bind(), checkfirst=False)
