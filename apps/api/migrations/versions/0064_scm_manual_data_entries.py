"""SCM manual data entry and source overlay lifecycle.

Revision ID: 0064_scm_manual_entries
Revises: 0063_tenant_business_indexes
"""
from alembic import op
import sqlalchemy as sa

revision = "0064_scm_manual_entries"
down_revision = "0063_tenant_business_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some 0062-era installations created all then-current SCM metadata in one
    # pass. Preserve compatibility with those databases and with clean rebuilds.
    if sa.inspect(op.get_bind()).has_table("scm_manual_data_entries"):
        return
    op.create_table(
        "scm_manual_data_entries",
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("material_id", sa.String(64), sa.ForeignKey("scm_materials.id"), nullable=False),
        sa.Column("canonical_material_id", sa.String(64), sa.ForeignKey("platform_materials.id"), nullable=True),
        sa.Column("target_entity_type", sa.String(80), nullable=True),
        sa.Column("target_entity_id", sa.String(64), nullable=True),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("previous_values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_authority", sa.String(80), nullable=False, server_default="genuinegigs_manual"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_membership_id", sa.String(64), sa.ForeignKey("workspace_memberships.id"), nullable=True),
        sa.Column("correlation_id", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("supersedes_entry_id", sa.String(64), sa.ForeignKey("scm_manual_data_entries.id"), nullable=True),
        sa.Column("planning_run_id", sa.String(64), sa.ForeignKey("scm_planning_runs.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("public_id", name="uq_scm_manual_data_entries_public_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_scm_manual_entry_idempotency"),
    )
    for column in ("entry_type", "material_id", "canonical_material_id", "target_entity_type", "target_entity_id", "supplier_id", "effective_at", "status", "created_by_user_id", "created_by_membership_id", "correlation_id", "planning_run_id", "tenant_id", "plant_id", "business_number", "public_id"):
        op.create_index(f"ix_scm_manual_data_entries_{column}", "scm_manual_data_entries", [column])


def downgrade() -> None:
    op.drop_table("scm_manual_data_entries")
