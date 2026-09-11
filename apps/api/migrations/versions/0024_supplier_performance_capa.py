"""Add evidence-linked supplier performance and corrective actions.

Revision ID: 0024_supplier_performance_capa
Revises: 0023_supplier_compliance
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_supplier_performance_capa"
down_revision = "0023_supplier_compliance"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "supplier_performance_events" not in inspector.get_table_names():
        op.create_table(
        "supplier_performance_events",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("plant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=True),
        sa.Column("source_entity_type", sa.String(64), nullable=False), sa.Column("source_entity_id", sa.String(64), nullable=False),
        sa.Column("metric_type", sa.String(48), nullable=False), sa.Column("numerator", sa.Float(), nullable=False),
        sa.Column("denominator", sa.Float(), nullable=False), sa.Column("score", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", "metric_type", name="uq_supplier_performance_source_metric"),
        sa.CheckConstraint("denominator > 0 AND score >= 0 AND score <= 100", name="ck_supplier_performance_score"),
    )
        for name, cols in (("ix_supplier_performance_events_tenant_id", ["tenant_id"]), ("ix_supplier_performance_events_plant_id", ["plant_id"]), ("ix_supplier_performance_events_supplier_id", ["supplier_id"]), ("ix_supplier_performance_events_metric_type", ["metric_type"]), ("ix_supplier_performance_events_occurred_at", ["occurred_at"])):
            op.create_index(name, "supplier_performance_events", cols)
    if "supplier_corrective_actions" not in inspector.get_table_names():
        op.create_table(
        "supplier_corrective_actions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("plant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("cases.id"), nullable=True),
        sa.Column("source_entity_type", sa.String(64), nullable=False), sa.Column("source_entity_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("requested_response_by", sa.DateTime(timezone=True), nullable=False), sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("corrective_action", sa.Text(), nullable=False), sa.Column("preventive_action", sa.Text(), nullable=False),
        sa.Column("effectiveness_evidence", sa.JSON(), nullable=False), sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.String(64), nullable=True),
        sa.CheckConstraint("status IN ('open','awaiting_supplier','response_received','effectiveness_review','closed','cancelled')", name="ck_supplier_corrective_action_status"),
    )
        for name, cols in (("ix_supplier_corrective_actions_tenant_id", ["tenant_id"]), ("ix_supplier_corrective_actions_plant_id", ["plant_id"]), ("ix_supplier_corrective_actions_supplier_id", ["supplier_id"]), ("ix_supplier_corrective_actions_status", ["status"]), ("ix_supplier_corrective_actions_requested_response_by", ["requested_response_by"])):
            op.create_index(name, "supplier_corrective_actions", cols)


def downgrade():
    pass
