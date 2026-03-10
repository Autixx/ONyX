"""add route policies

Revision ID: 0003_add_route_policies
Revises: 0002_add_job_locks
Create Date: 2026-03-10 19:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_add_route_policies"
down_revision: Union[str, Sequence[str], None] = "0002_add_job_locks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("ingress_interface", sa.String(length=32), nullable=False),
        sa.Column(
            "action",
            sa.Enum("DIRECT", "NEXT_HOP", name="route_policy_action"),
            nullable=False,
        ),
        sa.Column("target_interface", sa.String(length=32), nullable=False),
        sa.Column("target_gateway", sa.String(length=64), nullable=True),
        sa.Column("routed_networks", sa.JSON(), nullable=False),
        sa.Column("excluded_networks", sa.JSON(), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False, server_default=sa.text("51820")),
        sa.Column("rule_priority", sa.Integer(), nullable=False, server_default=sa.text("10000")),
        sa.Column("firewall_mark", sa.Integer(), nullable=False, server_default=sa.text("51820")),
        sa.Column("masquerade", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("applied_state", sa.JSON(), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "name", name="uq_route_policy_node_name"),
    )
    op.create_index(op.f("ix_route_policies_node_id"), "route_policies", ["node_id"], unique=False)
    op.create_index(op.f("ix_route_policies_enabled"), "route_policies", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_route_policies_enabled"), table_name="route_policies")
    op.drop_index(op.f("ix_route_policies_node_id"), table_name="route_policies")
    op.drop_table("route_policies")
    sa.Enum("DIRECT", "NEXT_HOP", name="route_policy_action").drop(op.get_bind(), checkfirst=True)
