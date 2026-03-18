"""add registration referral snapshot fields

Revision ID: 0026_registration_ref
Revises: 0025_node_agent_enum
Create Date: 2026-03-18 12:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_registration_ref"
down_revision = "0025_node_agent_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("registrations", sa.Column("resolved_plan_id", sa.String(length=36), nullable=True))
    op.add_column("registrations", sa.Column("consumed_referral_code_id", sa.String(length=36), nullable=True))
    op.add_column("registrations", sa.Column("referral_device_limit_override", sa.Integer(), nullable=True))
    op.add_column("registrations", sa.Column("referral_usage_goal_override", sa.String(length=32), nullable=True))
    op.add_column("registrations", sa.Column("referral_consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_registrations_resolved_plan_id"), "registrations", ["resolved_plan_id"], unique=False)
    op.create_index(op.f("ix_registrations_consumed_referral_code_id"), "registrations", ["consumed_referral_code_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_registrations_consumed_referral_code_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_resolved_plan_id"), table_name="registrations")
    op.drop_column("registrations", "referral_consumed_at")
    op.drop_column("registrations", "referral_usage_goal_override")
    op.drop_column("registrations", "referral_device_limit_override")
    op.drop_column("registrations", "consumed_referral_code_id")
    op.drop_column("registrations", "resolved_plan_id")
