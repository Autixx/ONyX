"""add node traffic suspension control

Revision ID: 0014_node_traffic_control
Revises: 0013_node_traffic_accounting
Create Date: 2026-03-14 23:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_node_traffic_control"
down_revision: Union[str, Sequence[str], None] = "0013_node_traffic_accounting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("traffic_suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("nodes", sa.Column("traffic_suspension_reason", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "traffic_suspension_reason")
    op.drop_column("nodes", "traffic_suspended_at")
