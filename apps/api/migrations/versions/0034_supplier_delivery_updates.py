"""Add immutable supplier delivery schedule updates.

Revision ID: 0034_supplier_delivery_updates
Revises: 0033_supplier_delivery_portal
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_supplier_delivery_updates"
down_revision = "0033_supplier_delivery_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "supplier_delivery_updates" in inspector.get_table_names():
        return
    op.create_table(
        "supplier_delivery_updates",
        sa.Column("asn_id", sa.String(64), sa.ForeignKey("asns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("po_draft_id", sa.String(64), sa.ForeignKey("po_drafts.id"), nullable=False),
        sa.Column("supplier_id", sa.String(64), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("external_update_id", sa.String(160), nullable=False),
        sa.Column("update_type", sa.String(48), nullable=False, server_default="schedule_change"),
        sa.Column("previous_expected_delivery", sa.String(32), nullable=False, server_default=""),
        sa.Column("revised_expected_delivery", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("business_number", sa.String(120), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "plant_id", "asn_id", "external_update_id", name="uq_supplier_delivery_update_external"),
        sa.CheckConstraint("update_type IN ('schedule_change','delay','expedite')", name="ck_supplier_delivery_update_type"),
    )
    for name, columns in (
        ("ix_supplier_delivery_updates_asn_id", ["asn_id"]),
        ("ix_supplier_delivery_updates_po_draft_id", ["po_draft_id"]),
        ("ix_supplier_delivery_updates_supplier_id", ["supplier_id"]),
        ("ix_supplier_delivery_updates_update_type", ["update_type"]),
        ("ix_supplier_delivery_updates_tenant_id", ["tenant_id"]),
        ("ix_supplier_delivery_updates_plant_id", ["plant_id"]),
        ("ix_supplier_delivery_updates_business_number", ["business_number"]),
        ("ix_supplier_delivery_updates_public_id", ["public_id"]),
    ):
        op.create_index(name, "supplier_delivery_updates", columns)


def downgrade() -> None:
    pass
