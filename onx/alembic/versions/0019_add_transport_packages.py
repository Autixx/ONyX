"""add transport packages

Revision ID: 0019_add_transport_packages
Revises: 0018_add_xray_services
Create Date: 2026-03-15 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_add_transport_packages"
down_revision = "0018_add_xray_services"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return table in sa_inspect(op.get_bind()).get_table_names()


def _index_exists(table: str, index_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return any(i["name"] == index_name for i in sa_inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _table_exists("transport_packages"):
        op.create_table(
            "transport_packages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("preferred_xray_service_id", sa.String(length=36), nullable=True),
            sa.Column("enable_xray", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enable_awg", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enable_wg", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("enable_openvpn_cloak", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("priority_order_json", sa.JSON(), nullable=False),
            sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_reconcile_summary_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["preferred_xray_service_id"], ["xray_services.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
    if not _index_exists("transport_packages", "ix_transport_packages_id"):
        op.create_index(op.f("ix_transport_packages_id"), "transport_packages", ["id"], unique=False)
    if not _index_exists("transport_packages", "ix_transport_packages_user_id"):
        op.create_index(op.f("ix_transport_packages_user_id"), "transport_packages", ["user_id"], unique=False)
    if not _index_exists("transport_packages", "ix_transport_packages_preferred_xray_service_id"):
        op.create_index(op.f("ix_transport_packages_preferred_xray_service_id"), "transport_packages", ["preferred_xray_service_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transport_packages_preferred_xray_service_id"), table_name="transport_packages")
    op.drop_index(op.f("ix_transport_packages_user_id"), table_name="transport_packages")
    op.drop_index(op.f("ix_transport_packages_id"), table_name="transport_packages")
    op.drop_table("transport_packages")
