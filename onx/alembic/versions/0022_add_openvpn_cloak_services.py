"""add openvpn cloak services

Revision ID: 0022_add_openvpn_cloak_services
Revises: 0021_add_wg_services
Create Date: 2026-03-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_add_openvpn_cloak_services"
down_revision = "0021_add_wg_services"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return table in sa_inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return column in [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect
    return any(i["name"] == index_name for i in sa_inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    service_state = postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="openvpn_cloak_service_state", create_type=False)
    service_state.create(op.get_bind(), checkfirst=True)

    if not _table_exists("openvpn_cloak_services"):
        op.create_table(
            "openvpn_cloak_services",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("node_id", sa.String(length=36), nullable=False),
            sa.Column("state", service_state, nullable=False),
            sa.Column("openvpn_local_host", sa.String(length=255), nullable=False),
            sa.Column("openvpn_local_port", sa.Integer(), nullable=False),
            sa.Column("cloak_listen_host", sa.String(length=255), nullable=False),
            sa.Column("cloak_listen_port", sa.Integer(), nullable=False),
            sa.Column("public_host", sa.String(length=255), nullable=False),
            sa.Column("public_port", sa.Integer(), nullable=True),
            sa.Column("server_name", sa.String(length=255), nullable=True),
            sa.Column("client_local_port", sa.Integer(), nullable=False),
            sa.Column("server_network_v4", sa.String(length=64), nullable=False),
            sa.Column("dns_server_v4", sa.String(length=64), nullable=True),
            sa.Column("mtu", sa.Integer(), nullable=False),
            sa.Column("client_allowed_ips_json", sa.JSON(), nullable=False),
            sa.Column("cloak_public_key", sa.String(length=128), nullable=True),
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
    if not _index_exists("openvpn_cloak_services", "ix_openvpn_cloak_services_id"):
        op.create_index(op.f("ix_openvpn_cloak_services_id"), "openvpn_cloak_services", ["id"], unique=False)
    if not _index_exists("openvpn_cloak_services", "ix_openvpn_cloak_services_name"):
        op.create_index(op.f("ix_openvpn_cloak_services_name"), "openvpn_cloak_services", ["name"], unique=False)
    if not _index_exists("openvpn_cloak_services", "ix_openvpn_cloak_services_node_id"):
        op.create_index(op.f("ix_openvpn_cloak_services_node_id"), "openvpn_cloak_services", ["node_id"], unique=False)
    if not _index_exists("openvpn_cloak_services", "ix_openvpn_cloak_services_state"):
        op.create_index(op.f("ix_openvpn_cloak_services_state"), "openvpn_cloak_services", ["state"], unique=False)

    if not _column_exists("peers", "openvpn_cloak_service_id"):
        op.add_column("peers", sa.Column("openvpn_cloak_service_id", sa.String(length=36), nullable=True))
    if not _column_exists("peers", "cloak_uid"):
        op.add_column("peers", sa.Column("cloak_uid", sa.String(length=128), nullable=True))
    if not _index_exists("peers", "ix_peers_openvpn_cloak_service_id"):
        op.create_index(op.f("ix_peers_openvpn_cloak_service_id"), "peers", ["openvpn_cloak_service_id"], unique=False)
    with op.batch_alter_table("peers") as batch_op:
        batch_op.create_foreign_key("fk_peers_openvpn_cloak_service_id", "openvpn_cloak_services", ["openvpn_cloak_service_id"], ["id"], ondelete="SET NULL")

    if not _column_exists("transport_packages", "preferred_openvpn_cloak_service_id"):
        op.add_column("transport_packages", sa.Column("preferred_openvpn_cloak_service_id", sa.String(length=36), nullable=True))
    if not _index_exists("transport_packages", "ix_transport_packages_preferred_openvpn_cloak_service_id"):
        op.create_index(
            op.f("ix_transport_packages_preferred_openvpn_cloak_service_id"),
            "transport_packages",
            ["preferred_openvpn_cloak_service_id"],
            unique=False,
        )
    with op.batch_alter_table("transport_packages") as batch_op:
        batch_op.create_foreign_key(
            "fk_transport_packages_preferred_openvpn_cloak_service_id",
            "openvpn_cloak_services",
            ["preferred_openvpn_cloak_service_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("transport_packages") as batch_op:
        batch_op.drop_constraint("fk_transport_packages_preferred_openvpn_cloak_service_id", type_="foreignkey")
    op.drop_index(op.f("ix_transport_packages_preferred_openvpn_cloak_service_id"), table_name="transport_packages")
    op.drop_column("transport_packages", "preferred_openvpn_cloak_service_id")

    with op.batch_alter_table("peers") as batch_op:
        batch_op.drop_constraint("fk_peers_openvpn_cloak_service_id", type_="foreignkey")
    op.drop_index(op.f("ix_peers_openvpn_cloak_service_id"), table_name="peers")
    op.drop_column("peers", "cloak_uid")
    op.drop_column("peers", "openvpn_cloak_service_id")

    op.drop_index(op.f("ix_openvpn_cloak_services_state"), table_name="openvpn_cloak_services")
    op.drop_index(op.f("ix_openvpn_cloak_services_node_id"), table_name="openvpn_cloak_services")
    op.drop_index(op.f("ix_openvpn_cloak_services_name"), table_name="openvpn_cloak_services")
    op.drop_index(op.f("ix_openvpn_cloak_services_id"), table_name="openvpn_cloak_services")
    op.drop_table("openvpn_cloak_services")

    service_state = postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="openvpn_cloak_service_state", create_type=False)
    service_state.drop(op.get_bind(), checkfirst=True)
