"""add transport package split tunnel fields

Revision ID: 0028_transport_package_split_tunnel
Revises: 0027_device_bans_and_subscription_windows
Create Date: 2026-03-18 15:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_transport_package_split_tunnel"
down_revision = "0027_device_bans_and_subscription_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transport_packages",
        sa.Column("split_tunnel_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "transport_packages",
        sa.Column("split_tunnel_routes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    with op.batch_alter_table("transport_packages") as batch_op:
        batch_op.alter_column("split_tunnel_enabled", existing_type=sa.Boolean(), server_default=None)
        batch_op.alter_column("split_tunnel_routes_json", existing_type=sa.JSON(), server_default=None)


def downgrade() -> None:
    op.drop_column("transport_packages", "split_tunnel_routes_json")
    op.drop_column("transport_packages", "split_tunnel_enabled")
