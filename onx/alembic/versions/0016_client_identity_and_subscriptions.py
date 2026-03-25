"""add client identity and subscription foundation

Revision ID: 0016_client_identity
Revises: 0015_node_traffic_harden
Create Date: 2026-03-14 23:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0016_client_identity"
down_revision: Union[str, Sequence[str], None] = "0015_node_traffic_harden"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_status = postgresql.ENUM("pending", "active", "blocked", "deleted", name="user_status", create_type=False)
    billing_mode = postgresql.ENUM("manual", "lifetime", "periodic", "trial", name="billing_mode", create_type=False)
    subscription_status = postgresql.ENUM("pending", "active", "suspended", "expired", "revoked", name="subscription_status", create_type=False)
    bind = op.get_bind()
    user_status.create(bind, checkfirst=True)
    billing_mode.create(bind, checkfirst=True)
    subscription_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("referral_code", sa.String(length=128), nullable=True),
        sa.Column("usage_goal", sa.String(length=32), nullable=True),
        sa.Column("requested_device_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("billing_mode", billing_mode, nullable=False, server_default="manual"),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("default_device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("default_usage_goal_policy", sa.String(length=32), nullable=True),
        sa.Column("traffic_quota_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plans_code"), "plans", ["code"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("status", subscription_status, nullable=False, server_default="active"),
        sa.Column("billing_mode", billing_mode, nullable=False, server_default="manual"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("traffic_quota_bytes", sa.BigInteger(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=False)
    op.create_index(op.f("ix_subscriptions_plan_id"), "subscriptions", ["plan_id"], unique=False)
    op.create_index(op.f("ix_subscriptions_expires_at"), "subscriptions", ["expires_at"], unique=False)

    op.create_table(
        "referral_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_limit_override", sa.Integer(), nullable=True),
        sa.Column("usage_goal_override", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_referral_codes_code"), "referral_codes", ["code"], unique=True)
    op.create_index(op.f("ix_referral_codes_plan_id"), "referral_codes", ["plan_id"], unique=False)

    op.create_table(
        "client_auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_client_auth_sessions_user_id"), "client_auth_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_client_auth_sessions_session_token_hash"), "client_auth_sessions", ["session_token_hash"], unique=True)
    op.create_index(op.f("ix_client_auth_sessions_expires_at"), "client_auth_sessions", ["expires_at"], unique=False)

    op.add_column("registrations", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("registrations", sa.Column("first_name", sa.String(length=128), nullable=True))
    op.add_column("registrations", sa.Column("last_name", sa.String(length=128), nullable=True))
    op.add_column("registrations", sa.Column("usage_goal", sa.String(length=32), nullable=True))
    op.add_column("registrations", sa.Column("reviewed_by", sa.String(length=36), nullable=True))
    op.add_column("registrations", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("registrations", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.add_column("registrations", sa.Column("approved_user_id", sa.String(length=36), nullable=True))
    op.add_column("registrations", sa.Column("auto_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_registrations_reviewed_by"), "registrations", ["reviewed_by"], unique=False)
    op.create_index(op.f("ix_registrations_approved_user_id"), "registrations", ["approved_user_id"], unique=False)
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.create_foreign_key("fk_registrations_reviewed_by_admin_users", "admin_users", ["reviewed_by"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_registrations_approved_user_id_users", "users", ["approved_user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    user_status = postgresql.ENUM("pending", "active", "blocked", "deleted", name="user_status", create_type=False)
    billing_mode = postgresql.ENUM("manual", "lifetime", "periodic", "trial", name="billing_mode", create_type=False)
    subscription_status = postgresql.ENUM("pending", "active", "suspended", "expired", "revoked", name="subscription_status", create_type=False)

    with op.batch_alter_table("registrations") as batch_op:
        batch_op.drop_constraint("fk_registrations_approved_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_registrations_reviewed_by_admin_users", type_="foreignkey")
    op.drop_index(op.f("ix_registrations_approved_user_id"), table_name="registrations")
    op.drop_index(op.f("ix_registrations_reviewed_by"), table_name="registrations")
    op.drop_column("registrations", "auto_approved_at")
    op.drop_column("registrations", "approved_user_id")
    op.drop_column("registrations", "reject_reason")
    op.drop_column("registrations", "reviewed_at")
    op.drop_column("registrations", "reviewed_by")
    op.drop_column("registrations", "usage_goal")
    op.drop_column("registrations", "last_name")
    op.drop_column("registrations", "first_name")
    op.drop_column("registrations", "password_hash")

    op.drop_index(op.f("ix_client_auth_sessions_expires_at"), table_name="client_auth_sessions")
    op.drop_index(op.f("ix_client_auth_sessions_session_token_hash"), table_name="client_auth_sessions")
    op.drop_index(op.f("ix_client_auth_sessions_user_id"), table_name="client_auth_sessions")
    op.drop_table("client_auth_sessions")

    op.drop_index(op.f("ix_referral_codes_plan_id"), table_name="referral_codes")
    op.drop_index(op.f("ix_referral_codes_code"), table_name="referral_codes")
    op.drop_table("referral_codes")

    op.drop_index(op.f("ix_subscriptions_expires_at"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_plan_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_user_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
    subscription_status.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_plans_code"), table_name="plans")
    op.drop_table("plans")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    billing_mode.drop(op.get_bind(), checkfirst=True)
    user_status.drop(op.get_bind(), checkfirst=True)
