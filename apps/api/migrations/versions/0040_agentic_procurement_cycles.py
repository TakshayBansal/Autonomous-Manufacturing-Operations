"""Durable procurement-cycle orchestration foundation."""
from alembic import op
import sqlalchemy as sa

revision = "0040_agentic_procurement_cycles"
down_revision = "0039_current_quotation_invariant"
branch_labels = None
depends_on = None

SCOPED = [
    sa.Column("id", sa.String(64), primary_key=True), sa.Column("public_id", sa.String(36), nullable=False),
    sa.Column("business_number", sa.String(80)), sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("plant_id", sa.String(64)), sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
]

def scoped(*columns, constraints=()):
    return [column.copy() for column in SCOPED] + list(columns) + list(constraints)

def upgrade() -> None:
    # The baseline migration intentionally snapshots current metadata for fresh
    # installations. In that path these objects already exist; this revision is
    # only responsible for incrementally upgraded databases.
    if "procurement_cycle_objectives" in sa.inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table("tasks") as batch:
        for name, kind in (("planned_start_at", sa.DateTime(timezone=True)), ("actual_start_at", sa.DateTime(timezone=True)),
            ("estimated_effort_minutes", sa.Integer), ("business_impact", sa.String(32)), ("production_impact", sa.String(32)),
            ("last_meaningful_activity_at", sa.DateTime(timezone=True)), ("blocker_type", sa.String(48)),
            ("blocker_owner_membership_id", sa.String(64)), ("rework_count", sa.Integer), ("quality_result", sa.String(48))):
            batch.add_column(sa.Column(name, kind, nullable=True))
    op.create_table("procurement_cycle_objectives", *scoped(
        sa.Column("requirement_id", sa.String(64), sa.ForeignKey("purchase_requirements.id"), nullable=False),
        sa.Column("requirement_line_id", sa.String(64), sa.ForeignKey("purchase_requirement_lines.id")),
        sa.Column("owner_membership_id", sa.String(64)), sa.Column("current_stage", sa.String(48), nullable=False),
        sa.Column("health", sa.String(32), nullable=False), sa.Column("need_by_date", sa.String(32)),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("aggregate_version", sa.Integer, nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True)), sa.Column("evaluation_summary", sa.JSON, nullable=False),
        constraints=(sa.UniqueConstraint("requirement_id", "requirement_line_id", name="uq_cycle_objective_root"),)))
    op.create_index("uq_cycle_objective_requirement_root", "procurement_cycle_objectives", ["requirement_id"], unique=True,
                    postgresql_where=sa.text("requirement_line_id IS NULL"), sqlite_where=sa.text("requirement_line_id IS NULL"))
    op.create_table("cycle_stage_states", *scoped(
        sa.Column("objective_id", sa.String(64), sa.ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", sa.String(48), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("owner_role", sa.String(64)), sa.Column("owner_membership_id", sa.String(64)),
        sa.Column("entered_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("evidence", sa.JSON, nullable=False), constraints=(sa.UniqueConstraint("objective_id", "stage_key", name="uq_cycle_stage"),)))
    op.create_table("cycle_dependencies", *scoped(
        sa.Column("objective_id", sa.String(64), sa.ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_type", sa.String(64), nullable=False), sa.Column("description", sa.Text, nullable=False),
        sa.Column("owner_membership_id", sa.String(64)), sa.Column("semantic_key", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        constraints=(sa.UniqueConstraint("objective_id", "semantic_key", name="uq_cycle_dependency_semantic"),)))
    op.create_table("cycle_risks", *scoped(
        sa.Column("objective_id", sa.String(64), sa.ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_type", sa.String(64), nullable=False), sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text, nullable=False), sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("semantic_key", sa.String(240), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        constraints=(sa.UniqueConstraint("objective_id", "semantic_key", name="uq_cycle_risk_semantic"),)))
    op.create_table("commitments", *scoped(
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objective_id", sa.String(64), sa.ForeignKey("procurement_cycle_objectives.id")),
        sa.Column("commitment_type", sa.String(32), nullable=False), sa.Column("owner_membership_id", sa.String(64)),
        sa.Column("promised_at", sa.DateTime(timezone=True), nullable=False), sa.Column("deliverable", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("revision", sa.Integer, nullable=False), sa.Column("revision_reason", sa.Text)))
    op.create_table("agent_prepared_work_items", *scoped(
        sa.Column("objective_id", sa.String(64), sa.ForeignKey("procurement_cycle_objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id")), sa.Column("owner_membership_id", sa.String(64)),
        sa.Column("work_type", sa.String(64), nullable=False), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.JSON, nullable=False), sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("semantic_key", sa.String(240), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("generating_run_id", sa.String(64)), constraints=(sa.UniqueConstraint("objective_id", "semantic_key", name="uq_prepared_work_semantic"),)))
    op.create_table("event_outbox", *scoped(
        sa.Column("event_id", sa.String(64), nullable=False, unique=True), sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False), sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("aggregate_version", sa.Integer, nullable=False), sa.Column("actor_membership_id", sa.String(64)),
        sa.Column("correlation_id", sa.String(80), nullable=False), sa.Column("causation_id", sa.String(80)),
        sa.Column("payload", sa.JSON, nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False), sa.Column("processed_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.Text)))

def downgrade() -> None:
    for table in ("event_outbox", "agent_prepared_work_items", "commitments", "cycle_risks", "cycle_dependencies", "cycle_stage_states", "procurement_cycle_objectives"):
        op.drop_table(table)
    with op.batch_alter_table("tasks") as batch:
        for name in ("quality_result", "rework_count", "blocker_owner_membership_id", "blocker_type", "last_meaningful_activity_at", "production_impact", "business_impact", "estimated_effort_minutes", "actual_start_at", "planned_start_at"):
            batch.drop_column(name)
