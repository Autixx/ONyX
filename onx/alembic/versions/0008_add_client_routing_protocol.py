"""add client routing protocol tables

Revision ID: 0008_add_client_routing_protocol
Revises: 0007_add_probe_results
Create Date: 2026-03-11 20:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008_add_client_routing_protocol"
down_revision: Union[str, Sequence[str], None] = "0007_add_probe_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("session_token", sa.String(length=128), nullable=False),
        sa.Column("client_public_ip", sa.String(length=64), nullable=True),
        sa.Column("client_country_code", sa.String(length=8), nullable=True),
        sa.Column("destination_country_code", sa.String(length=8), nullable=True),
        sa.Column("current_ingress_node_id", sa.String(length=36), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rebind_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["current_ingress_node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_client_sessions_device_id"), "client_sessions", ["device_id"], unique=False)
    op.create_index(op.f("ix_client_sessions_session_token"), "client_sessions", ["session_token"], unique=True)
    op.create_index(op.f("ix_client_sessions_current_ingress_node_id"), "client_sessions", ["current_ingress_node_id"], unique=False)
    op.create_index(op.f("ix_client_sessions_expires_at"), "client_sessions", ["expires_at"], unique=False)

    op.create_table(
        "client_probes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=True),
        sa.Column("rtt_ms", sa.Float(), nullable=True),
        sa.Column("jitter_ms", sa.Float(), nullable=True),
        sa.Column("loss_pct", sa.Float(), nullable=True),
        sa.Column("handshake_ms", sa.Float(), nullable=True),
        sa.Column("throughput_mbps", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["client_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_client_probes_session_id"), "client_probes", ["session_id"], unique=False)
    op.create_index(op.f("ix_client_probes_node_id"), "client_probes", ["node_id"], unique=False)
    op.create_index(op.f("ix_client_probes_score"), "client_probes", ["score"], unique=False)
    op.create_index(op.f("ix_client_probes_reported_at"), "client_probes", ["reported_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_client_probes_reported_at"), table_name="client_probes")
    op.drop_index(op.f("ix_client_probes_score"), table_name="client_probes")
    op.drop_index(op.f("ix_client_probes_node_id"), table_name="client_probes")
    op.drop_index(op.f("ix_client_probes_session_id"), table_name="client_probes")
    op.drop_table("client_probes")

    op.drop_index(op.f("ix_client_sessions_expires_at"), table_name="client_sessions")
    op.drop_index(op.f("ix_client_sessions_current_ingress_node_id"), table_name="client_sessions")
    op.drop_index(op.f("ix_client_sessions_session_token"), table_name="client_sessions")
    op.drop_index(op.f("ix_client_sessions_device_id"), table_name="client_sessions")
    op.drop_table("client_sessions")
