"""Customer commitments and shared action plans.

Revision ID: 0073_case_execution_core
Revises: 0072_gigi_companion_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0073_case_execution_core"
down_revision = "0072_gigi_companion_state"
branch_labels = None
depends_on = None


def common():
    return [sa.Column("id", sa.String(64), primary_key=True), sa.Column("public_id", sa.String(36), nullable=False, unique=True),
            sa.Column("business_number", sa.String(80)), sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64)), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    if "platform_action_plans" in set(sa.inspect(op.get_bind()).get_table_names()): return
    op.create_table("platform_customer_orders", *common(), sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("order_number", sa.String(120), nullable=False), sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("source_record_id", sa.String(180), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_system", "source_record_id", name="uq_platform_customer_order_source"))
    op.create_table("platform_customer_order_lines", *common(),
        sa.Column("customer_order_id", sa.String(64), sa.ForeignKey("platform_customer_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.String(48), nullable=False), sa.Column("product_id", sa.String(64), sa.ForeignKey("platform_products.id"), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("uom", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("customer_order_id", "line_number", name="uq_platform_customer_order_line"))
    op.create_table("platform_action_plans", *common(),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("platform_operational_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_record_id", sa.String(64), sa.ForeignKey("platform_decision_records.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("strategy_type", sa.String(80), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False), sa.Column("expected_outcome", sa.JSON(), nullable=False))
    op.create_table("platform_action_plan_steps", *common(),
        sa.Column("action_plan_id", sa.String(64), sa.ForeignKey("platform_action_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("owner_team", sa.String(80), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("dependency_step_ids", sa.JSON(), nullable=False),
        sa.Column("action_intent_id", sa.String(64), sa.ForeignKey("platform_action_intents.id")),
        sa.Column("evidence_requirement", sa.Text()), sa.UniqueConstraint("action_plan_id", "sequence", name="uq_platform_action_plan_step"))
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("commitments")}
    for column in (sa.Column("operational_case_id", sa.String(64)), sa.Column("related_entity_type", sa.String(80)),
                   sa.Column("related_entity_id", sa.String(64)), sa.Column("completion_condition", sa.JSON()),
                   sa.Column("escalation_condition", sa.JSON()), sa.Column("evidence_requirement", sa.Text()),
                   sa.Column("next_evaluation_at", sa.DateTime(timezone=True)),
                   sa.Column("dependency_state", sa.String(32), server_default="INTERNAL")):
        if column.name not in columns:
            op.add_column("commitments", column)


def downgrade():
    for table in ("platform_action_plan_steps", "platform_action_plans", "platform_customer_order_lines", "platform_customer_orders"):
        op.drop_table(table)
