"""Fix install AGH job_kind enum label case.

Revision ID: 0039_fix_install_agh_job_kind_enum_case
Revises: 0038_add_job_kind_install_agh
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_fix_install_agh_job_kind_enum_case"
down_revision = "0038_add_job_kind_install_agh"
branch_labels = None
depends_on = None


def _enum_labels(bind) -> set[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname = 'job_kind'
            """
        )
    ).fetchall()
    return {str(row[0]) for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    labels = _enum_labels(bind)
    if "INSTALL_AGH" in labels:
        return
    if "install_agh" in labels:
        op.execute("ALTER TYPE job_kind RENAME VALUE 'install_agh' TO 'INSTALL_AGH'")
        return
    op.execute("ALTER TYPE job_kind ADD VALUE IF NOT EXISTS 'INSTALL_AGH'")


def downgrade() -> None:
    # Keep enum label as-is; in-place enum downgrades are intentionally omitted.
    pass
