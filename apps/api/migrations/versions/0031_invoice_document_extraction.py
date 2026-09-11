"""Add governed supplier-invoice document extraction.

Revision ID: 0031_invoice_document_extraction
Revises: 0030_structured_inbound_exceptions
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_invoice_document_extraction"
down_revision = "0030_structured_inbound_exceptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "invoice_extraction_runs" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "invoice_extraction_runs",
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=True),
        sa.Column("invoice_id", sa.String(64), sa.ForeignKey("supplier_invoices.id"), nullable=True),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("verified_fields", sa.JSON(), nullable=False),
        sa.Column("verified_by_user_id", sa.String(64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False, unique=True),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "business_number", name="uq_invoice_extraction_runs_tenant_business_number"),
    )
    op.create_index("ix_invoice_extraction_runs_document_id", "invoice_extraction_runs", ["document_id"])
    op.create_index("ix_invoice_extraction_runs_po_draft_id", "invoice_extraction_runs", ["po_draft_id"])
    op.create_index("ix_invoice_extraction_runs_invoice_id", "invoice_extraction_runs", ["invoice_id"])
    op.create_index("ix_invoice_extraction_runs_status", "invoice_extraction_runs", ["status"])
    op.create_index("ix_invoice_extraction_runs_public_id", "invoice_extraction_runs", ["public_id"], unique=True)
    op.create_index("ix_invoice_extraction_runs_business_number", "invoice_extraction_runs", ["business_number"])
    op.create_index("ix_invoice_extraction_runs_tenant_id", "invoice_extraction_runs", ["tenant_id"])
    op.create_index("ix_invoice_extraction_runs_plant_id", "invoice_extraction_runs", ["plant_id"])


def downgrade() -> None:
    op.drop_table("invoice_extraction_runs")
