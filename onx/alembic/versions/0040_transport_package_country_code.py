"""add split_tunnel_country_code to transport_packages

Revision ID: 0040_transport_package_country_code
Revises: 0039_fix_install_agh_job_kind_enum_case
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0040_transport_package_country_code"
down_revision = "0039_fix_install_agh_job_kind_enum_case"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transport_packages",
        sa.Column("split_tunnel_country_code", sa.String(8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transport_packages", "split_tunnel_country_code")
