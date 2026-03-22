"""Add support_tickets table.

Revision ID: 0034_support_tickets
Revises: 0033_referral_pools
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_support_tickets"
down_revision = "0033_referral_pools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("device_id", sa.String(36), nullable=True),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("diagnostics", sa.JSON, nullable=True),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("support_tickets")
