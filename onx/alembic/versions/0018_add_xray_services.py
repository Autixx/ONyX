"""add xray services

Revision ID: 0018_add_xray_services
Revises: 0017_devices_and_bundles
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_add_xray_services"
down_revision = "0017_devices_and_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    transport_mode = postgresql.ENUM("vless_xhttp", name="xray_service_transport_mode", create_type=False)
    service_state = postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="xray_service_state", create_type=False)
    bind = op.get_bind()
    transport_mode.create(bind, checkfirst=True)
    service_state.create(bind, checkfirst=True)

    op.create_table(
        "xray_services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "node_id",
            sa.String(length=36),
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transport_mode",
            transport_mode,
            nullable=False,
        ),
        sa.Column(
            "state",
            service_state,
            nullable=False,
        ),
        sa.Column("listen_host", sa.String(length=255), nullable=False),
        sa.Column("listen_port", sa.Integer(), nullable=False),
        sa.Column("public_host", sa.String(length=255), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=True),
        sa.Column("server_name", sa.String(length=255), nullable=True),
        sa.Column("xhttp_path", sa.String(length=255), nullable=False),
        sa.Column("tls_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("desired_config_json", sa.JSON(), nullable=True),
        sa.Column("applied_config_json", sa.JSON(), nullable=True),
        sa.Column("health_summary_json", sa.JSON(), nullable=True),
        sa.Column("last_error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_xray_services_name"), "xray_services", ["name"], unique=True)
    op.create_index(op.f("ix_xray_services_node_id"), "xray_services", ["node_id"], unique=False)
    op.create_index(op.f("ix_xray_services_state"), "xray_services", ["state"], unique=False)

    op.add_column(
        "peers",
        sa.Column("xray_service_id", sa.String(length=36), nullable=True),
    )
    op.create_index(op.f("ix_peers_xray_service_id"), "peers", ["xray_service_id"], unique=False)
    with op.batch_alter_table("peers") as batch_op:
        batch_op.create_foreign_key(
            "fk_peers_xray_service_id_xray_services",
            "xray_services",
            ["xray_service_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("peers") as batch_op:
        batch_op.drop_constraint("fk_peers_xray_service_id_xray_services", type_="foreignkey")
    op.drop_index(op.f("ix_peers_xray_service_id"), table_name="peers")
    op.drop_column("peers", "xray_service_id")

    op.drop_index(op.f("ix_xray_services_state"), table_name="xray_services")
    op.drop_index(op.f("ix_xray_services_node_id"), table_name="xray_services")
    op.drop_index(op.f("ix_xray_services_name"), table_name="xray_services")
    op.drop_table("xray_services")
    postgresql.ENUM("planned", "applying", "active", "failed", "deleted", name="xray_service_state", create_type=False).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM("vless_xhttp", name="xray_service_transport_mode", create_type=False).drop(op.get_bind(), checkfirst=True)
