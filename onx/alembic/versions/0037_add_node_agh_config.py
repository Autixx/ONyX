"""Add AGH (AdGuard Home) config columns to nodes.

Revision ID: 0037_add_node_agh_config
Revises: 0036_support_ticket_status
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_add_node_agh_config"
down_revision = "0036_support_ticket_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("agh_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("nodes", sa.Column("agh_host", sa.String(255), nullable=True))
    op.add_column("nodes", sa.Column("agh_port", sa.Integer(), nullable=True))
    op.add_column("nodes", sa.Column("agh_web_user", sa.String(128), nullable=True))
    op.add_column("nodes", sa.Column("agh_web_password", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "agh_web_password")
    op.drop_column("nodes", "agh_web_user")
    op.drop_column("nodes", "agh_port")
    op.drop_column("nodes", "agh_host")
    op.drop_column("nodes", "agh_enabled")
