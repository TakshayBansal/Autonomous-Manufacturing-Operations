"""Incremental shared core platform contracts.

Revision ID: 0058_core_platform_foundation
Revises: 0057_scm_control_tower_scaffold
"""
from alembic import op
import sqlalchemy as sa

from app.db.models import Base

revision = "0058_core_platform_foundation"
down_revision = "0057_scm_control_tower_scaffold"
branch_labels = None
depends_on = None

TABLE_NAMES = [
    "platform_materials", "platform_material_sites", "external_entity_references",
    "data_provenance", "data_quality_issues", "platform_material_state_projections",
    "platform_action_intents", "platform_action_policy_evaluations", "platform_action_approvals",
    "platform_action_executions", "platform_operational_cases",
    "platform_action_outcomes",
]


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLE_NAMES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    columns = {item["name"] for item in sa.inspect(bind).get_columns("event_outbox")}
    additions = [
        ("event_version", sa.Column("event_version", sa.Integer(), nullable=False, server_default="1")),
        ("occurred_at", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)),
        ("recorded_at", sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True)),
        ("source_system", sa.Column("source_system", sa.String(length=100), nullable=True)),
        ("subject_type", sa.Column("subject_type", sa.String(length=80), nullable=True)),
        ("subject_id", sa.Column("subject_id", sa.String(length=64), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("event_outbox", column)
    op.execute("UPDATE event_outbox SET occurred_at = created_at WHERE occurred_at IS NULL")
    op.execute("UPDATE event_outbox SET recorded_at = created_at WHERE recorded_at IS NULL")
    op.execute("UPDATE event_outbox SET source_system = 'legacy' WHERE source_system IS NULL")
    op.execute("UPDATE event_outbox SET subject_type = aggregate_type WHERE subject_type IS NULL")
    op.execute("UPDATE event_outbox SET subject_id = aggregate_id WHERE subject_id IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    # Envelope columns are deliberately retained: historical event records
    # must remain replayable even if a deploy rolls back application code.
