"""Ensure node_secret_kind contains AGENT_TOKEN enum value.

Revision ID: 0025_node_agent_enum
Revises: 0024_transit_failover
Create Date: 2026-03-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0025_node_agent_enum"
down_revision: Union[str, Sequence[str], None] = "0024_transit_failover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE node_secret_kind ADD VALUE IF NOT EXISTS 'AGENT_TOKEN'")


def downgrade() -> None:
    # PostgreSQL enum values are not removed in place on downgrade.
    pass
