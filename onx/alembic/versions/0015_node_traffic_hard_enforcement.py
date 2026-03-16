"""add node traffic hard enforcement fields

Revision ID: 0015_node_traffic_harden
Revises: 0014_node_traffic_control
Create Date: 2026-03-14 20:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_node_traffic_harden"
down_revision = "0014_node_traffic_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("traffic_hard_enforced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("nodes", sa.Column("traffic_hard_enforcement_reason", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "traffic_hard_enforcement_reason")
    op.drop_column("nodes", "traffic_hard_enforced_at")
