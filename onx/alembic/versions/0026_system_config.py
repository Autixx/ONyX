"""Create system_config table for operator-managed key-value settings.

Revision ID: 0026_system_config
Revises: 0025_node_agent_enum
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0026_system_config"
down_revision: Union[str, Sequence[str], None] = "0030_node_gateway_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("system_config")
