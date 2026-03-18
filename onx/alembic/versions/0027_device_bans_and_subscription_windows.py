"""add device bans and subscription access windows

Revision ID: 0027_device_bans_and_subscription_windows
Revises: 0026_registration_ref
Create Date: 2026-03-18 12:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_device_bans_and_subscription_windows"
down_revision = "0026_registration_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'device_status' AND e.enumlabel = 'banned'
            ) THEN
                ALTER TYPE device_status ADD VALUE 'banned';
            END IF;
        END$$;
        """
    )
    op.add_column("devices", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("ban_reason", sa.String(length=255), nullable=True))

    op.add_column(
        "subscriptions",
        sa.Column("access_window_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "subscriptions",
        sa.Column("access_days_mask", sa.Integer(), nullable=False, server_default=sa.text("127")),
    )
    op.add_column("subscriptions", sa.Column("access_window_start_local", sa.String(length=5), nullable=True))
    op.add_column("subscriptions", sa.Column("access_window_end_local", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "access_window_end_local")
    op.drop_column("subscriptions", "access_window_start_local")
    op.drop_column("subscriptions", "access_days_mask")
    op.drop_column("subscriptions", "access_window_enabled")

    op.drop_column("devices", "ban_reason")
    op.drop_column("devices", "banned_until")
    op.drop_column("devices", "banned_at")
