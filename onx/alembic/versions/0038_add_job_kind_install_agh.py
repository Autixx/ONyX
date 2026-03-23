"""Add install_agh value to job_kind enum.

Revision ID: 0038_add_job_kind_install_agh
Revises: 0037_add_node_agh_config
Create Date: 2026-03-23
"""

from alembic import op

revision = "0038_add_job_kind_install_agh"
down_revision = "0037_add_node_agh_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE job_kind ADD VALUE IF NOT EXISTS 'INSTALL_AGH'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed in place.
    pass
