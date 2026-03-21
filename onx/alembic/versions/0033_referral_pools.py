"""Add referral_pools table and pool_id to referral_codes.

Revision ID: 0033_referral_pools
Revises: 0032_plan_schedule
Create Date: 2026-03-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: Union[str, Sequence[str], None] = "0033_referral_pools"
down_revision: Union[str, Sequence[str], None] = "0032_plan_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_pools",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=True, index=True),
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
    )

    op.add_column("referral_codes", sa.Column("pool_id", sa.String(36), nullable=True))
    with op.batch_alter_table("referral_codes") as batch_op:
        batch_op.create_index("ix_referral_codes_pool_id", ["pool_id"])
        batch_op.create_foreign_key(
            "fk_referral_codes_pool_id",
            "referral_pools",
            ["pool_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("referral_codes") as batch_op:
        batch_op.drop_constraint("fk_referral_codes_pool_id", type_="foreignkey")
        batch_op.drop_index("ix_referral_codes_pool_id")
    op.drop_column("referral_codes", "pool_id")
    op.drop_table("referral_pools")
