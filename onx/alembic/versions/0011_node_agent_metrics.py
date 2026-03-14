"""Add node agent auth and peer traffic state.

Revision ID: 0011_node_agent_metrics
Revises: 0010_add_admin_web_auth
Create Date: 2026-03-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_node_agent_metrics"
down_revision: Union[str, Sequence[str], None] = "0010_add_admin_web_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE node_secret_kind ADD VALUE IF NOT EXISTS 'agent_token'")

    op.create_table(
        "peer_registries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("peer_public_key", sa.String(length=128), nullable=False),
        sa.Column("first_node_id", sa.String(length=36), nullable=True),
        sa.Column("first_interface_name", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["first_node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_peer_registries_peer_public_key"), "peer_registries", ["peer_public_key"], unique=True)
    op.create_index(op.f("ix_peer_registries_first_node_id"), "peer_registries", ["first_node_id"], unique=False)

    op.create_table(
        "peer_traffic_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("peer_public_key", sa.String(length=128), nullable=False),
        sa.Column("interface_name", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("allowed_ips_json", sa.JSON(), nullable=False),
        sa.Column("rx_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tx_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latest_handshake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_version", sa.String(length=32), nullable=True),
        sa.Column("agent_hostname", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "interface_name", "peer_public_key", name="uq_peer_traffic_node_iface_peer"),
    )
    op.create_index(op.f("ix_peer_traffic_states_node_id"), "peer_traffic_states", ["node_id"], unique=False)
    op.create_index(op.f("ix_peer_traffic_states_peer_public_key"), "peer_traffic_states", ["peer_public_key"], unique=False)
    op.create_index(op.f("ix_peer_traffic_states_interface_name"), "peer_traffic_states", ["interface_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_peer_traffic_states_interface_name"), table_name="peer_traffic_states")
    op.drop_index(op.f("ix_peer_traffic_states_peer_public_key"), table_name="peer_traffic_states")
    op.drop_index(op.f("ix_peer_traffic_states_node_id"), table_name="peer_traffic_states")
    op.drop_table("peer_traffic_states")

    op.drop_index(op.f("ix_peer_registries_first_node_id"), table_name="peer_registries")
    op.drop_index(op.f("ix_peer_registries_peer_public_key"), table_name="peer_registries")
    op.drop_table("peer_registries")
