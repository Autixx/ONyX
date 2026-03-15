"""add transit policies

Revision ID: 0023_add_transit_policies
Revises: 0022_add_openvpn_cloak_services
Create Date: 2026-03-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_add_transit_policies"
down_revision = "0022_add_openvpn_cloak_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    transit_policy_state = sa.Enum(
        "planned",
        "applying",
        "active",
        "failed",
        "degraded",
        "deleted",
        name="transit_policy_state",
    )
    transit_policy_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "transit_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("state", transit_policy_state, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ingress_interface", sa.String(length=32), nullable=False),
        sa.Column("transparent_port", sa.Integer(), nullable=False),
        sa.Column("firewall_mark", sa.Integer(), nullable=False),
        sa.Column("route_table_id", sa.Integer(), nullable=False),
        sa.Column("rule_priority", sa.Integer(), nullable=False),
        sa.Column("ingress_service_kind", sa.String(length=64), nullable=True),
        sa.Column("ingress_service_ref_id", sa.String(length=64), nullable=True),
        sa.Column("next_hop_kind", sa.String(length=64), nullable=True),
        sa.Column("next_hop_ref_id", sa.String(length=64), nullable=True),
        sa.Column("capture_protocols_json", sa.JSON(), nullable=False),
        sa.Column("capture_cidrs_json", sa.JSON(), nullable=False),
        sa.Column("excluded_cidrs_json", sa.JSON(), nullable=False),
        sa.Column("management_bypass_ipv4_json", sa.JSON(), nullable=False),
        sa.Column("management_bypass_tcp_ports_json", sa.JSON(), nullable=False),
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
    op.create_index(op.f("ix_transit_policies_id"), "transit_policies", ["id"], unique=False)
    op.create_index(op.f("ix_transit_policies_name"), "transit_policies", ["name"], unique=False)
    op.create_index(op.f("ix_transit_policies_node_id"), "transit_policies", ["node_id"], unique=False)
    op.create_index(op.f("ix_transit_policies_state"), "transit_policies", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transit_policies_state"), table_name="transit_policies")
    op.drop_index(op.f("ix_transit_policies_node_id"), table_name="transit_policies")
    op.drop_index(op.f("ix_transit_policies_name"), table_name="transit_policies")
    op.drop_index(op.f("ix_transit_policies_id"), table_name="transit_policies")
    op.drop_table("transit_policies")
    sa.Enum(
        "planned",
        "applying",
        "active",
        "failed",
        "degraded",
        "deleted",
        name="transit_policy_state",
    ).drop(op.get_bind(), checkfirst=True)
