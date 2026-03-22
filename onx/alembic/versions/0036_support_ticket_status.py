"""Add status and auto-close columns to support_tickets.

Revision ID: 0036_support_ticket_status
Revises: 0035_support_chat_messages
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_support_ticket_status"
down_revision = "0035_support_chat_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_tickets",
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column(
        "support_tickets",
        sa.Column("last_client_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column("last_operator_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "support_tickets",
        sa.Column(
            "autoclose_warning_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("support_tickets", "autoclose_warning_sent")
    op.drop_column("support_tickets", "last_operator_message_at")
    op.drop_column("support_tickets", "last_client_message_at")
    op.drop_column("support_tickets", "status")
