"""add probe results

Revision ID: 0007_add_probe_results
Revises: 0006_add_balancers_and_route_policy_balancer
Create Date: 2026-03-10 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_add_probe_results"
down_revision: Union[str, Sequence[str], None] = "0006_add_balancers_and_route_policy_balancer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "probe_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "probe_type",
            sa.Enum("PING", "INTERFACE_LOAD", name="probe_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("SUCCESS", "FAILED", "DEGRADED", name="probe_status"),
            nullable=False,
            server_default=sa.text("'SUCCESS'"),
        ),
        sa.Column("source_node_id", sa.String(length=36), nullable=True),
        sa.Column("balancer_id", sa.String(length=36), nullable=True),
        sa.Column("member_interface", sa.String(length=32), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["balancer_id"], ["balancers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_probe_results_probe_type"), "probe_results", ["probe_type"], unique=False)
    op.create_index(op.f("ix_probe_results_status"), "probe_results", ["status"], unique=False)
    op.create_index(op.f("ix_probe_results_source_node_id"), "probe_results", ["source_node_id"], unique=False)
    op.create_index(op.f("ix_probe_results_balancer_id"), "probe_results", ["balancer_id"], unique=False)
    op.create_index(op.f("ix_probe_results_member_interface"), "probe_results", ["member_interface"], unique=False)
    op.create_index(op.f("ix_probe_results_created_at"), "probe_results", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_probe_results_created_at"), table_name="probe_results")
    op.drop_index(op.f("ix_probe_results_member_interface"), table_name="probe_results")
    op.drop_index(op.f("ix_probe_results_balancer_id"), table_name="probe_results")
    op.drop_index(op.f("ix_probe_results_source_node_id"), table_name="probe_results")
    op.drop_index(op.f("ix_probe_results_status"), table_name="probe_results")
    op.drop_index(op.f("ix_probe_results_probe_type"), table_name="probe_results")
    op.drop_table("probe_results")
    sa.Enum("SUCCESS", "FAILED", "DEGRADED", name="probe_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum("PING", "INTERFACE_LOAD", name="probe_type").drop(op.get_bind(), checkfirst=True)
