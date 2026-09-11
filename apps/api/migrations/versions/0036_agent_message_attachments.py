"""Persist agent message evidence and resumable document state."""

from alembic import op
import sqlalchemy as sa


revision = "0036_agent_message_attachments"
down_revision = "0035_scoped_public_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy baseline migration creates current metadata for a brand-new
    # database. Incremental production upgrades do not, so support both paths.
    if "agent_message_attachments" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "agent_message_attachments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_id", sa.String(64), sa.ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("file_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purpose", sa.String(48), nullable=False, server_default="evidence"),
        sa.Column("status", sa.String(48), nullable=False, server_default="queued"),
        sa.Column("document_job_id", sa.String(64), sa.ForeignKey("document_jobs.id"), nullable=True),
        sa.Column("inferred_rfq_id", sa.String(64), nullable=True),
        sa.Column("confirmed_rfq_id", sa.String(64), nullable=True),
        sa.Column("inferred_supplier_id", sa.String(64), nullable=True),
        sa.Column("confirmed_supplier_id", sa.String(64), nullable=True),
        sa.Column("inference_confidence", sa.Float(), nullable=True),
        sa.Column("inference_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("linked_quotation_id", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("user_explanation", sa.Text(), nullable=True),
        sa.UniqueConstraint("message_id", "document_id", name="uq_agent_message_document"),
    )
    for column in (
        "public_id", "business_number", "tenant_id", "plant_id", "message_id",
        "document_id", "status", "document_job_id", "inferred_rfq_id",
        "confirmed_rfq_id", "inferred_supplier_id", "confirmed_supplier_id",
        "linked_quotation_id",
    ):
        op.create_index(f"ix_agent_message_attachments_{column}", "agent_message_attachments", [column])


def downgrade() -> None:
    op.drop_table("agent_message_attachments")
