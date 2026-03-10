"""add dns policies

Revision ID: 0004_add_dns_policies
Revises: 0003_add_route_policies
Create Date: 2026-03-10 19:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_add_dns_policies"
down_revision: Union[str, Sequence[str], None] = "0003_add_route_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dns_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("route_policy_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("dns_address", sa.String(length=64), nullable=False),
        sa.Column("capture_protocols", sa.JSON(), nullable=False),
        sa.Column("capture_ports", sa.JSON(), nullable=False),
        sa.Column("exceptions_networks", sa.JSON(), nullable=False),
        sa.Column("applied_state", sa.JSON(), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["route_policy_id"], ["route_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_policy_id", name="uq_dns_policy_route_policy"),
    )
    op.create_index(op.f("ix_dns_policies_route_policy_id"), "dns_policies", ["route_policy_id"], unique=False)
    op.create_index(op.f("ix_dns_policies_enabled"), "dns_policies", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dns_policies_enabled"), table_name="dns_policies")
    op.drop_index(op.f("ix_dns_policies_route_policy_id"), table_name="dns_policies")
    op.drop_table("dns_policies")
