"""Add canonical invoice matching and finance handoff records."""
from alembic import op
import sqlalchemy as sa

revision = "0016_invoice_matching"
down_revision = "0015_connector_controls"
branch_labels = None
depends_on = None

SCOPED = [
    sa.Column("id", sa.String(64), primary_key=True), sa.Column("public_id", sa.String(36), nullable=False, unique=True),
    sa.Column("business_number", sa.String(80), nullable=True, unique=True), sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("plant_id", sa.String(64), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
]

def table(name: str, *args) -> None:
    op.create_table(name, *[column.copy() for column in SCOPED], *args)

def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "supplier_invoices" not in existing:
        table("supplier_invoices", sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False), sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=True), sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=True), sa.Column("invoice_number", sa.String(120), nullable=False), sa.Column("invoice_date", sa.String(32), nullable=False), sa.Column("currency", sa.String(16), nullable=False), sa.Column("subtotal", sa.Float(), nullable=False), sa.Column("tax_amount", sa.Float(), nullable=False), sa.Column("total_amount", sa.Float(), nullable=False), sa.Column("status", sa.String(48), nullable=False), sa.Column("source", sa.String(48), nullable=False), sa.Column("content_hash", sa.String(64), nullable=True), sa.UniqueConstraint("tenant_id", "plant_id", "supplier_id", "invoice_number", name="uq_supplier_invoice_number_scope"), sa.CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="ck_invoice_amounts_nonnegative"))
    if "supplier_invoice_lines" not in existing:
        table("supplier_invoice_lines", sa.Column("invoice_id", sa.String(64), sa.ForeignKey("supplier_invoices.id", ondelete="CASCADE"), nullable=False), sa.Column("po_line_id", sa.String(64), sa.ForeignKey("po_draft_lines.id"), nullable=True), sa.Column("item_id", sa.String(64), sa.ForeignKey("items.id"), nullable=True), sa.Column("description", sa.Text(), nullable=False), sa.Column("quantity", sa.Float(), nullable=False), sa.Column("uom", sa.String(32), nullable=False), sa.Column("unit_price", sa.Float(), nullable=False), sa.Column("tax_amount", sa.Float(), nullable=False), sa.Column("line_total", sa.Float(), nullable=False), sa.CheckConstraint("quantity >= 0 AND unit_price >= 0 AND line_total >= 0", name="ck_invoice_line_amounts_nonnegative"))
    if "invoice_match_results" not in existing:
        table("invoice_match_results", sa.Column("invoice_id", sa.String(64), sa.ForeignKey("supplier_invoices.id"), nullable=False), sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=False), sa.Column("receipt_id", sa.String(64), sa.ForeignKey("store_receipts.id"), nullable=True), sa.Column("match_type", sa.String(32), nullable=False), sa.Column("result", sa.String(32), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("variances", sa.JSON(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("policy_version", sa.String(32), nullable=False), sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False))
    if "finance_handoffs" not in existing:
        table("finance_handoffs", sa.Column("invoice_id", sa.String(64), sa.ForeignKey("supplier_invoices.id"), nullable=False), sa.Column("match_result_id", sa.String(64), sa.ForeignKey("invoice_match_results.id"), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("prepared_by_user_id", sa.String(64), nullable=False), sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("invoice_id", "match_result_id", name="uq_invoice_match_finance_handoff"))

def downgrade() -> None:
    for name in ("finance_handoffs", "invoice_match_results", "supplier_invoice_lines", "supplier_invoices"):
        op.drop_table(name)
