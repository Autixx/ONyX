"""add balancers and balancer route policy support

Revision ID: 0006_add_balancers_and_route_policy_balancer
Revises: 0005_add_geo_policies
Create Date: 2026-03-10 20:35:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_add_balancers_and_route_policy_balancer"
down_revision: Union[str, Sequence[str], None] = "0005_add_geo_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.create_table(
        "balancers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column(
            "method",
            sa.Enum("RANDOM", "LEASTLOAD", "LEASTPING", name="balancer_method"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("state_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "name", name="uq_balancer_node_name"),
    )
    op.create_index(op.f("ix_balancers_node_id"), "balancers", ["node_id"], unique=False)
    op.create_index(op.f("ix_balancers_name"), "balancers", ["name"], unique=False)

    if dialect == "postgresql":
        op.execute("ALTER TYPE route_policy_action ADD VALUE IF NOT EXISTS 'BALANCER'")

    with op.batch_alter_table("route_policies", schema=None) as batch_op:
        if dialect != "postgresql":
            batch_op.alter_column(
                "action",
                existing_type=sa.Enum("DIRECT", "NEXT_HOP", name="route_policy_action"),
                type_=sa.Enum("DIRECT", "NEXT_HOP", "BALANCER", name="route_policy_action"),
                existing_nullable=False,
            )
        batch_op.add_column(sa.Column("balancer_id", sa.String(length=36), nullable=True))
        batch_op.create_index(op.f("ix_route_policies_balancer_id"), ["balancer_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_route_policies_balancer_id_balancers",
            "balancers",
            ["balancer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.alter_column(
            "target_interface",
            existing_type=sa.String(length=32),
            nullable=True,
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table("route_policies", schema=None) as batch_op:
        batch_op.alter_column(
            "target_interface",
            existing_type=sa.String(length=32),
            nullable=False,
        )
        batch_op.drop_constraint("fk_route_policies_balancer_id_balancers", type_="foreignkey")
        batch_op.drop_index(op.f("ix_route_policies_balancer_id"))
        batch_op.drop_column("balancer_id")
        if dialect != "postgresql":
            batch_op.alter_column(
                "action",
                existing_type=sa.Enum("DIRECT", "NEXT_HOP", "BALANCER", name="route_policy_action"),
                type_=sa.Enum("DIRECT", "NEXT_HOP", name="route_policy_action"),
                existing_nullable=False,
            )

    op.drop_index(op.f("ix_balancers_name"), table_name="balancers")
    op.drop_index(op.f("ix_balancers_node_id"), table_name="balancers")
    op.drop_table("balancers")
    sa.Enum("RANDOM", "LEASTLOAD", "LEASTPING", name="balancer_method").drop(op.get_bind(), checkfirst=True)
