"""Add per-day access schedule and exception dates to plans.

Revision ID: 0032_plan_schedule
Revises: 0031_subscription_refactor
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: Union[str, Sequence[str], None] = "0032_plan_schedule"
down_revision: Union[str, Sequence[str], None] = "0031_subscription_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("access_schedule_json", sa.JSON(), nullable=True))
    op.add_column("plans", sa.Column("access_exception_dates_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "access_exception_dates_json")
    op.drop_column("plans", "access_schedule_json")
