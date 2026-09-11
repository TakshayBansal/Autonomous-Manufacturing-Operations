"""Harden the shared core for deep SCM development.

Revision ID: 0060_scm_readiness_core_hardening
Revises: 0059_core_platform_completion
"""
from alembic import op
import sqlalchemy as sa

from app.db.models import Base

revision = "0060_scm_readiness_core_hardening"
down_revision = "0059_core_platform_completion"
branch_labels = None
depends_on = None

NEW_TABLES = [
    "platform_purchase_orders", "platform_purchase_order_lines",
    "platform_work_order_references", "platform_scenario_definitions",
    "platform_simulation_runs",
]

ALTERS = {
    "platform_entity_relationships": [
        sa.Column("source_system", sa.String(100), nullable=False, server_default="genuinegigs"),
        sa.Column("provenance_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
    ],
    "platform_state_snapshots": [sa.Column("correlation_id", sa.String(80), nullable=True)],
    "data_provenance": [sa.Column("correlation_id", sa.String(80), nullable=True)],
    "platform_action_intents": [
        sa.Column("originating_case_id", sa.String(64), nullable=True),
        sa.Column("reason_code", sa.String(120), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("expected_impact", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="medium"),
    ],
    "platform_action_executions": [
        sa.Column("external_reference", sa.String(240), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    ],
    "platform_operational_cases": [
        sa.Column("correlation_id", sa.String(80), nullable=True),
        sa.Column("canonical_entity_type", sa.String(80), nullable=True),
        sa.Column("canonical_entity_id", sa.String(64), nullable=True),
        sa.Column("resolution_evidence", sa.JSON(), nullable=False, server_default="[]"),
    ],
    "event_outbox": [
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, additions in ALTERS.items():
        existing = {item["name"] for item in inspector.get_columns(table)}
        for column in additions:
            if column.name not in existing:
                op.add_column(table, column)
    for name in NEW_TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    for table, additions in reversed(list(ALTERS.items())):
        for column in reversed(additions):
            op.drop_column(table, column.name)
