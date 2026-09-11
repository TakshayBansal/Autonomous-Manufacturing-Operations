"""Add review-before-create quotation intakes."""

from alembic import op
import sqlalchemy as sa


revision = "0038_quotation_intakes"
down_revision = "0037_agent_thread_state_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "quotation_intakes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "quotation_intakes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("rfq_id", sa.String(64), sa.ForeignKey("rfqs.id"), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("document_job_id", sa.String(64), sa.ForeignKey("document_jobs.id"), nullable=True),
        sa.Column("extraction_run_id", sa.String(64), sa.ForeignKey("quote_extraction_runs.id"), nullable=True),
        sa.Column("inferred_supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("confirmed_supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("quote_id", sa.String(64), sa.ForeignKey("supplier_quotes.id"), nullable=True),
        sa.Column("extracted_fields", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("supplier_candidates", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("provider", sa.String(48), nullable=False, server_default=""),
        sa.Column("provider_job_id", sa.String(160), nullable=True),
        sa.Column("parser_version", sa.String(80), nullable=False, server_default=""),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(64), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('parsed','manual_comparison')", name="ck_quotation_intake_mode"),
        sa.CheckConstraint(
            "status IN ('queued','extracting','needs_review','needs_manual_entry','failed','accepted')",
            name="ck_quotation_intake_status",
        ),
        sa.UniqueConstraint("document_id", name="uq_quotation_intakes_document_id"),
    )
    for column in ("tenant_id", "plant_id", "mode", "status", "rfq_id", "document_id", "document_job_id", "extraction_run_id", "inferred_supplier_id", "confirmed_supplier_id", "quote_id"):
        op.create_index(f"ix_quotation_intakes_{column}", "quotation_intakes", [column])


def downgrade() -> None:
    op.drop_table("quotation_intakes")
