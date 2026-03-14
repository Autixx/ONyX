"""add node traffic accounting cycles

Revision ID: 0013_node_traffic_accounting
Revises: 0012_web_ui_modules
Create Date: 2026-03-14 23:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_node_traffic_accounting"
down_revision: Union[str, Sequence[str], None] = "0012_web_ui_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_traffic_cycles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("cycle_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rx_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tx_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("warning_emitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exceeded_emitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "cycle_started_at", "cycle_ends_at", name="uq_node_traffic_cycle_window"),
    )
    op.create_index(op.f("ix_node_traffic_cycles_node_id"), "node_traffic_cycles", ["node_id"], unique=False)
    op.create_index(
        op.f("ix_node_traffic_cycles_cycle_started_at"),
        "node_traffic_cycles",
        ["cycle_started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_node_traffic_cycles_cycle_started_at"), table_name="node_traffic_cycles")
    op.drop_index(op.f("ix_node_traffic_cycles_node_id"), table_name="node_traffic_cycles")
    op.drop_table("node_traffic_cycles")
