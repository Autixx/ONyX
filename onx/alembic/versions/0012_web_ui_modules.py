"""add web ui support modules

Revision ID: 0012_web_ui_modules
Revises: 0011_node_agent_metrics
Create Date: 2026-03-14 16:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_web_ui_modules"
down_revision: Union[str, Sequence[str], None] = "0011_node_agent_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    registration_status = postgresql.ENUM("pending", "approved", "rejected", name="registration_status", create_type=False)
    registration_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "nodes",
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.add_column("nodes", sa.Column("traffic_limit_gb", sa.Float(), nullable=True))
    op.execute("UPDATE nodes SET registered_at = COALESCE(registered_at, created_at)")
    op.alter_column("nodes", "registered_at", nullable=False)

    op.create_table(
        "registrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("referral_code", sa.String(length=128), nullable=True),
        sa.Column("device_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", registration_status, nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_registrations_username"), "registrations", ["username"], unique=False)
    op.create_index(op.f("ix_registrations_email"), "registrations", ["email"], unique=False)

    op.create_table(
        "peers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("config_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.String(length=255), nullable=True),
        sa.Column("traffic_24h_mb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("traffic_month_mb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_peers_username"), "peers", ["username"], unique=False)
    op.create_index(op.f("ix_peers_email"), "peers", ["email"], unique=False)
    op.create_index(op.f("ix_peers_node_id"), "peers", ["node_id"], unique=False)


def downgrade() -> None:
    registration_status = postgresql.ENUM("pending", "approved", "rejected", name="registration_status", create_type=False)

    op.drop_index(op.f("ix_peers_node_id"), table_name="peers")
    op.drop_index(op.f("ix_peers_email"), table_name="peers")
    op.drop_index(op.f("ix_peers_username"), table_name="peers")
    op.drop_table("peers")

    op.drop_index(op.f("ix_registrations_email"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_username"), table_name="registrations")
    op.drop_table("registrations")
    registration_status.drop(op.get_bind(), checkfirst=True)

    op.drop_column("nodes", "traffic_limit_gb")
    op.drop_column("nodes", "registered_at")
