"""add geo policies

Revision ID: 0005_add_geo_policies
Revises: 0004_add_dns_policies
Create Date: 2026-03-10 20:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_add_geo_policies"
down_revision: Union[str, Sequence[str], None] = "0004_add_dns_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geo_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("route_policy_id", sa.String(length=36), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("DIRECT", "MULTIHOP", name="geo_policy_mode"),
            nullable=False,
        ),
        sa.Column("source_url_template", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["route_policy_id"], ["route_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_policy_id", "country_code", name="uq_geo_policy_route_country"),
    )
    op.create_index(op.f("ix_geo_policies_route_policy_id"), "geo_policies", ["route_policy_id"], unique=False)
    op.create_index(op.f("ix_geo_policies_enabled"), "geo_policies", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_geo_policies_enabled"), table_name="geo_policies")
    op.drop_index(op.f("ix_geo_policies_route_policy_id"), table_name="geo_policies")
    op.drop_table("geo_policies")
    sa.Enum("DIRECT", "MULTIHOP", name="geo_policy_mode").drop(op.get_bind(), checkfirst=True)
