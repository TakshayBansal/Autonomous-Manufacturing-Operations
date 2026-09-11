"""Add supplier compliance requirements and certificate evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0023_supplier_compliance"
down_revision = "0022_po_versions_amendments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "supplier_compliance_requirements" not in inspector.get_table_names():
        op.create_table(
            "supplier_compliance_requirements",
            sa.Column("certificate_type", sa.String(120), nullable=False), sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("item_id", sa.String(64), sa.ForeignKey("items.id"), nullable=True), sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("business_number", sa.String(80), nullable=True), sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("plant_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tenant_id", "plant_id", "certificate_type", "item_id", name="uq_supplier_compliance_requirement"),
        )
        for column in ("certificate_type", "item_id", "active", "tenant_id", "plant_id"):
            op.create_index(f"ix_supplier_compliance_requirements_{column}", "supplier_compliance_requirements", [column])
    if "supplier_certificates" not in inspector.get_table_names():
        op.create_table(
            "supplier_certificates",
            sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False), sa.Column("certificate_type", sa.String(120), nullable=False),
            sa.Column("certificate_number", sa.String(160), nullable=False, server_default=""), sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("valid_from", sa.String(32), nullable=False, server_default=""), sa.Column("expires_on", sa.String(32), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending_review"), sa.Column("verified_by_user_id", sa.String(64), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True), sa.Column("review_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("id", sa.String(64), primary_key=True), sa.Column("business_number", sa.String(80), nullable=True), sa.Column("tenant_id", sa.String(64), nullable=False), sa.Column("plant_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("status IN ('pending_review','verified','rejected','superseded')", name="ck_supplier_certificate_status"),
        )
        for column in ("supplier_id", "certificate_type", "document_id", "expires_on", "status", "tenant_id", "plant_id"):
            op.create_index(f"ix_supplier_certificates_{column}", "supplier_certificates", [column])


def downgrade() -> None:
    pass
