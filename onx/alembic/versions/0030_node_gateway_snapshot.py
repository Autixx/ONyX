"""add node gateway snapshot

Revision ID: 0030_node_gateway_snapshot
Revises: 0029_node_interface_snapshot
Create Date: 2026-03-19 18:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_node_gateway_snapshot"
down_revision = "0029_node_interface_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("discovered_gateways_json", sa.JSON(), nullable=True))
    op.execute("UPDATE nodes SET discovered_gateways_json = '{}'::json WHERE discovered_gateways_json IS NULL")
    op.alter_column("nodes", "discovered_gateways_json", nullable=False)


def downgrade() -> None:
    op.drop_column("nodes", "discovered_gateways_json")
