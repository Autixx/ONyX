"""add admin web auth tables

Revision ID: 0010_add_admin_web_auth
Revises: 0009_add_access_rules
Create Date: 2026-03-12 20:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0010_add_admin_web_auth"
down_revision: Union[str, Sequence[str], None] = "0009_add_access_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("roles_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_users_username"), "admin_users", ["username"], unique=True)

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_sessions_admin_user_id"), "admin_sessions", ["admin_user_id"], unique=False)
    op.create_index(op.f("ix_admin_sessions_session_token_hash"), "admin_sessions", ["session_token_hash"], unique=True)
    op.create_index(op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_admin_sessions_revoked_at"), "admin_sessions", ["revoked_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_sessions_revoked_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_expires_at"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_session_token_hash"), table_name="admin_sessions")
    op.drop_index(op.f("ix_admin_sessions_admin_user_id"), table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index(op.f("ix_admin_users_username"), table_name="admin_users")
    op.drop_table("admin_users")
