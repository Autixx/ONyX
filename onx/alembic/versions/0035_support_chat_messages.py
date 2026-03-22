"""Add support_chat_messages table.

Revision ID: 0035_support_chat_messages
Revises: 0034_support_tickets
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_support_chat_messages"
down_revision = "0034_support_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sender", sa.String(8), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("support_chat_messages")
