"""add access rules table

Revision ID: 0009_add_access_rules
Revises: 0008_add_client_routing_protocol
Create Date: 2026-03-11 22:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009_add_access_rules"
down_revision: Union[str, Sequence[str], None] = "0008_add_client_routing_protocol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("permission_key", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_roles_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_access_rules_permission_key"), "access_rules", ["permission_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_access_rules_permission_key"), table_name="access_rules")
    op.drop_table("access_rules")
