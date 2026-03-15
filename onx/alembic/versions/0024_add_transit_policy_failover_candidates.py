"""add transit policy failover candidates

Revision ID: 0024_add_transit_policy_failover_candidates
Revises: 0023_add_transit_policies
Create Date: 2026-03-15 18:40:00.000000
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0024_add_transit_policy_failover_candidates"
down_revision = "0023_add_transit_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transit_policies",
        sa.Column("next_hop_candidates_json", sa.JSON(), nullable=True),
    )

    bind = op.get_bind()
    transit_policies = sa.table(
        "transit_policies",
        sa.column("id", sa.String(length=36)),
        sa.column("next_hop_kind", sa.String(length=64)),
        sa.column("next_hop_ref_id", sa.String(length=64)),
        sa.column("next_hop_candidates_json", sa.JSON()),
    )

    rows = bind.execute(
        sa.select(
            transit_policies.c.id,
            transit_policies.c.next_hop_kind,
            transit_policies.c.next_hop_ref_id,
        )
    ).fetchall()
    for row in rows:
        candidates: list[dict[str, str]] = []
        kind = (row.next_hop_kind or "").strip()
        ref_id = (row.next_hop_ref_id or "").strip()
        if kind and ref_id:
            candidates.append({"kind": kind, "ref_id": ref_id})
        bind.execute(
            transit_policies.update()
            .where(transit_policies.c.id == row.id)
            .values(next_hop_candidates_json=json.loads(json.dumps(candidates)))
        )

    op.alter_column(
        "transit_policies",
        "next_hop_candidates_json",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("transit_policies", "next_hop_candidates_json")
