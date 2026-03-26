"""add quick deploy sessions

Revision ID: 0042_add_quick_deploy_sessions
Revises: 0041_add_xray_reality_fields
Create Date: 2026-03-26 03:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0042_add_quick_deploy_sessions"
down_revision = "0041_add_xray_reality_fields"
branch_labels = None
depends_on = None


def _job_target_type_labels(bind) -> set[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'job_target_type'
            """
        )
    )
    return {str(row[0]) for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    labels = _job_target_type_labels(bind)
    for label in (
        "AWG_SERVICE",
        "WG_SERVICE",
        "XRAY_SERVICE",
        "OPENVPN_CLOAK_SERVICE",
        "TRANSIT_POLICY",
    ):
        if label not in labels:
            op.execute(f"ALTER TYPE job_target_type ADD VALUE '{label}'")
            labels.add(label)

    op.create_table(
        "quick_deploy_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=128), nullable=True),
        sa.Column("request_payload_json", sa.JSON(), nullable=False),
        sa.Column("resources_json", sa.JSON(), nullable=False),
        sa.Column("child_jobs_json", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quick_deploy_sessions_scenario"), "quick_deploy_sessions", ["scenario"], unique=False)
    op.create_index(op.f("ix_quick_deploy_sessions_state"), "quick_deploy_sessions", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quick_deploy_sessions_state"), table_name="quick_deploy_sessions")
    op.drop_index(op.f("ix_quick_deploy_sessions_scenario"), table_name="quick_deploy_sessions")
    op.drop_table("quick_deploy_sessions")
