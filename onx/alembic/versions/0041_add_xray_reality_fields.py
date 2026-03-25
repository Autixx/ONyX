"""add xray reality fields

Revision ID: 0041_add_xray_reality_fields
Revises: 0040_transport_package_country_code
Create Date: 2026-03-26 01:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0041_add_xray_reality_fields"
down_revision = "0040_transport_package_country_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("xray_services", sa.Column("reality_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("xray_services", sa.Column("reality_dest", sa.String(length=255), nullable=True))
    op.add_column("xray_services", sa.Column("reality_private_key", sa.Text(), nullable=True))
    op.add_column("xray_services", sa.Column("reality_public_key", sa.Text(), nullable=True))
    op.add_column("xray_services", sa.Column("reality_short_id", sa.String(length=32), nullable=True))
    op.add_column("xray_services", sa.Column("reality_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("xray_services", sa.Column("reality_spider_x", sa.String(length=255), nullable=True))
    op.alter_column("xray_services", "reality_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("xray_services", "reality_spider_x")
    op.drop_column("xray_services", "reality_fingerprint")
    op.drop_column("xray_services", "reality_short_id")
    op.drop_column("xray_services", "reality_public_key")
    op.drop_column("xray_services", "reality_private_key")
    op.drop_column("xray_services", "reality_dest")
    op.drop_column("xray_services", "reality_enabled")
