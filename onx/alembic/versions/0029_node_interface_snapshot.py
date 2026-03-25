"""add node interface snapshot

Revision ID: 0029_node_interface_snapshot
Revises: 0028_transport_package_split_tunnel
Create Date: 2026-03-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0029_node_interface_snapshot"
down_revision: str | None = "0028_transport_package_split_tunnel"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column("discovered_interfaces_json", sa.JSON(), nullable=True),
    )
    op.execute("UPDATE nodes SET discovered_interfaces_json = '[]' WHERE discovered_interfaces_json IS NULL")
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("discovered_interfaces_json", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column("nodes", "discovered_interfaces_json")
