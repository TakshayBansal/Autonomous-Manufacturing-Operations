"""Add versioned procurement policies and immutable evaluations.

Revision ID: 0028_procurement_policy_engine
Revises: 0027_tenant_scoped_business_numbers
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_procurement_policy_engine"
down_revision = "0027_tenant_scoped_business_numbers"
branch_labels = None
depends_on = None


def _scoped_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False, unique=True),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "procurement_policies" not in existing_tables:
        op.create_table(
            "procurement_policies",
            *_scoped_columns(),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("rules", sa.JSON(), nullable=False),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by_user_id", sa.String(64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("status IN ('draft','active','retired')", name="ck_procurement_policy_status"),
            sa.UniqueConstraint("tenant_id", "plant_id", "name", "policy_version", name="uq_procurement_policy_version"),
            sa.UniqueConstraint("tenant_id", "business_number", name="uq_procurement_policies_tenant_business_number"),
        )
        op.create_index("ix_procurement_policies_tenant_id", "procurement_policies", ["tenant_id"])
        op.create_index("ix_procurement_policies_plant_id", "procurement_policies", ["plant_id"])
        op.create_index("ix_procurement_policies_status", "procurement_policies", ["status"])
    if "procurement_policy_evaluations" not in existing_tables:
        op.create_table(
            "procurement_policy_evaluations",
            *_scoped_columns(),
            sa.Column("policy_id", sa.String(64), sa.ForeignKey("procurement_policies.id"), nullable=True),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("entity_type", sa.String(64), nullable=False),
            sa.Column("entity_id", sa.String(64), nullable=False),
            sa.Column("entity_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("findings", sa.JSON(), nullable=False),
            sa.Column("required_approval_roles", sa.JSON(), nullable=False),
            sa.Column("evaluated_by_user_id", sa.String(64), nullable=False),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("decision IN ('pass','requires_justification','blocked')", name="ck_procurement_policy_evaluation_decision"),
            sa.UniqueConstraint("tenant_id", "entity_type", "entity_id", "entity_version", "policy_version", name="uq_procurement_policy_evaluation"),
            sa.UniqueConstraint("tenant_id", "business_number", name="uq_procurement_policy_evaluations_tenant_business_number"),
        )
        for column in ("tenant_id", "plant_id", "policy_id", "entity_type", "entity_id", "decision"):
            op.create_index(f"ix_procurement_policy_evaluations_{column}", "procurement_policy_evaluations", [column])


def downgrade() -> None:
    op.drop_table("procurement_policy_evaluations")
    op.drop_table("procurement_policies")
