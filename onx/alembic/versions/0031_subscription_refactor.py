"""Subscription refactor: merge Plan fields, standalone TransportPackages.

Adds to plans:
  - speed_limit_kbps, comment, fixed_expires_at, transport_package_id
  - access_window_enabled, access_days_mask, access_window_start_local,
    access_window_end_local
  - 'fixed_date' billing_mode enum value

Adds to transport_packages:
  - name column
  - Makes user_id nullable (removes NOT NULL + unique; adds partial unique index
    so each user still has at most one package)

Revision ID: 0031_subscription_refactor
Revises: 0026_system_config
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0031_subscription_refactor"
down_revision: Union[str, Sequence[str], None] = "0026_system_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── plans: new columns ────────────────────────────────────────────────────
    op.add_column("plans", sa.Column("speed_limit_kbps", sa.Integer(), nullable=True))
    op.add_column("plans", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("fixed_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("plans", sa.Column("transport_package_id", sa.String(36), nullable=True))
    op.add_column("plans", sa.Column("access_window_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("plans", sa.Column("access_days_mask", sa.Integer(), nullable=False, server_default="127"))
    op.add_column("plans", sa.Column("access_window_start_local", sa.String(5), nullable=True))
    op.add_column("plans", sa.Column("access_window_end_local", sa.String(5), nullable=True))

    # FK: plans.transport_package_id → transport_packages.id (SET NULL)
    with op.batch_alter_table("plans") as batch_op:
        batch_op.create_foreign_key(
            "fk_plans_transport_package_id",
            "transport_packages",
            ["transport_package_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ── plans: add 'fixed_date' to billing_mode enum (PostgreSQL only) ────────
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE billing_mode ADD VALUE IF NOT EXISTS 'fixed_date'")

    # ── transport_packages: add name column ───────────────────────────────────
    op.add_column("transport_packages", sa.Column("name", sa.String(128), nullable=True))

    # ── transport_packages: make user_id nullable, replace unique constraint ──
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE transport_packages ALTER COLUMN user_id DROP NOT NULL")
        # Drop the old column-level unique constraint (name may vary)
        op.execute("""
            DO $$
            DECLARE r RECORD;
            BEGIN
              FOR r IN
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'transport_packages'::regclass
                  AND contype = 'u'
                  AND conname ILIKE '%user_id%'
              LOOP
                EXECUTE 'ALTER TABLE transport_packages DROP CONSTRAINT IF EXISTS ' || quote_ident(r.conname);
              END LOOP;
            END $$;
        """)
        # Partial unique index: each user still limited to one package
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tp_user_id_partial
            ON transport_packages (user_id)
            WHERE user_id IS NOT NULL
        """)
    elif bind.dialect.name == "sqlite":
        # SQLite ALTER COLUMN not supported; user_id stays non-null for now.
        # New template rows can be inserted with user_id = NULL only on
        # PostgreSQL (production). Dev environment is SQLite — skip.
        pass


def downgrade() -> None:
    bind = op.get_bind()

    # transport_packages
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_tp_user_id_partial")
        op.execute("ALTER TABLE transport_packages ALTER COLUMN user_id SET NOT NULL")
        op.execute("""
            ALTER TABLE transport_packages
            ADD CONSTRAINT uq_transport_packages_user_id UNIQUE (user_id)
        """)

    op.drop_column("transport_packages", "name")

    # plans
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint("fk_plans_transport_package_id", type_="foreignkey")

    op.drop_column("plans", "access_window_end_local")
    op.drop_column("plans", "access_window_start_local")
    op.drop_column("plans", "access_days_mask")
    op.drop_column("plans", "access_window_enabled")
    op.drop_column("plans", "transport_package_id")
    op.drop_column("plans", "fixed_expires_at")
    op.drop_column("plans", "comment")
    op.drop_column("plans", "speed_limit_kbps")
    # PostgreSQL enum values cannot be removed without recreating the type
