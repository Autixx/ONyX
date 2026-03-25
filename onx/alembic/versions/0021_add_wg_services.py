"""add wg services

Revision ID: 0021_add_wg_services
Revises: 0020_add_awg_services
Create Date: 2026-03-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0021_add_wg_services"
down_revision = "0020_add_awg_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    wg_service_state = postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="wg_service_state", create_type=False)
    wg_service_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "wg_services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("state", wg_service_state, nullable=False),
        sa.Column("interface_name", sa.String(length=32), nullable=False),
        sa.Column("listen_host", sa.String(length=255), nullable=False),
        sa.Column("listen_port", sa.Integer(), nullable=False),
        sa.Column("public_host", sa.String(length=255), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=True),
        sa.Column("server_address_v4", sa.String(length=64), nullable=False),
        sa.Column("dns_server_v4", sa.String(length=64), nullable=True),
        sa.Column("mtu", sa.Integer(), nullable=False),
        sa.Column("persistent_keepalive", sa.Integer(), nullable=False),
        sa.Column("client_allowed_ips_json", sa.JSON(), nullable=False),
        sa.Column("server_public_key", sa.String(length=128), nullable=True),
        sa.Column("desired_config_json", sa.JSON(), nullable=True),
        sa.Column("applied_config_json", sa.JSON(), nullable=True),
        sa.Column("health_summary_json", sa.JSON(), nullable=True),
        sa.Column("last_error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_wg_services_id"), "wg_services", ["id"], unique=False)
    op.create_index(op.f("ix_wg_services_name"), "wg_services", ["name"], unique=False)
    op.create_index(op.f("ix_wg_services_node_id"), "wg_services", ["node_id"], unique=False)
    op.create_index(op.f("ix_wg_services_state"), "wg_services", ["state"], unique=False)

    op.add_column("peers", sa.Column("wg_service_id", sa.String(length=36), nullable=True))
    op.add_column("peers", sa.Column("wg_public_key", sa.String(length=128), nullable=True))
    op.add_column("peers", sa.Column("wg_address_v4", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_peers_wg_service_id"), "peers", ["wg_service_id"], unique=False)
    with op.batch_alter_table("peers") as batch_op:
        batch_op.create_foreign_key(None, "wg_services", ["wg_service_id"], ["id"], ondelete="SET NULL")

    op.add_column("transport_packages", sa.Column("preferred_wg_service_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_transport_packages_preferred_wg_service_id"), "transport_packages", ["preferred_wg_service_id"], unique=False)
    with op.batch_alter_table("transport_packages") as batch_op:
        batch_op.create_foreign_key(
            None,
            "wg_services",
            ["preferred_wg_service_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("transport_packages") as batch_op:
        batch_op.drop_constraint(None, type_="foreignkey")
    op.drop_index(op.f("ix_transport_packages_preferred_wg_service_id"), table_name="transport_packages")
    op.drop_column("transport_packages", "preferred_wg_service_id")

    with op.batch_alter_table("peers") as batch_op:
        batch_op.drop_constraint(None, type_="foreignkey")
    op.drop_index(op.f("ix_peers_wg_service_id"), table_name="peers")
    op.drop_column("peers", "wg_address_v4")
    op.drop_column("peers", "wg_public_key")
    op.drop_column("peers", "wg_service_id")

    op.drop_index(op.f("ix_wg_services_state"), table_name="wg_services")
    op.drop_index(op.f("ix_wg_services_node_id"), table_name="wg_services")
    op.drop_index(op.f("ix_wg_services_name"), table_name="wg_services")
    op.drop_index(op.f("ix_wg_services_id"), table_name="wg_services")
    op.drop_table("wg_services")

    wg_service_state = postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="wg_service_state", create_type=False)
    wg_service_state.drop(op.get_bind(), checkfirst=True)
