"""SCM phases 0-3 planning, risk and readiness models.

Revision ID: 0061_scm_phases_0_3
Revises: 0060_scm_readiness_core_hardening
"""
from alembic import op
import sqlalchemy as sa

from app.db.models import Base

revision = "0061_scm_phases_0_3"
down_revision = "0060_scm_readiness_core_hardening"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "scm_planning_profiles", "scm_demand_plans", "scm_demand_buckets",
    "scm_planning_input_snapshots", "scm_shortage_windows", "scm_material_risks",
    "scm_product_readiness", "scm_component_readiness", "scm_planning_run_deltas",
]

RUN_COLUMNS = [
    sa.Column("planning_profile_id", sa.String(64), nullable=True),
    sa.Column("demand_plan_id", sa.String(64), nullable=True),
    sa.Column("input_snapshot_id", sa.String(64), nullable=True),
    sa.Column("trigger_type", sa.String(32), nullable=False, server_default="MANUAL"),
    sa.Column("correlation_id", sa.String(80), nullable=True),
    sa.Column("summary_json", sa.JSON(), nullable=False, server_default="{}"),
]

POINT_COLUMNS = [
    sa.Column("canonical_material_id", sa.String(64), nullable=True),
    sa.Column("confirmed_receipts", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("planned_receipts", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("gross_demand", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("reserved_demand", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("projected_after_safety", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("shortage_qty", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("excess_qty", sa.Numeric(20, 6), nullable=False, server_default="0"),
    sa.Column("runway_days", sa.Integer(), nullable=True),
    sa.Column("planning_status", sa.String(24), nullable=False, server_default="UNKNOWN"),
    sa.Column("source_freshness", sa.JSON(), nullable=False, server_default="{}"),
]


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    # Profiles and demand must exist before snapshots/results that reference them.
    for name in NEW_TABLES[:3]:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    _add_missing("scm_planning_runs", RUN_COLUMNS)
    _add_missing("scm_material_projection_points", POINT_COLUMNS)
    for name in NEW_TABLES[3:]:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    for column in reversed(POINT_COLUMNS):
        op.drop_column("scm_material_projection_points", column.name)
    for column in reversed(RUN_COLUMNS):
        op.drop_column("scm_planning_runs", column.name)
