"""Add governed plant-knowledge scope, validity and citations."""
from alembic import op
import sqlalchemy as sa

revision = "0046_v2_knowledge_metadata"
down_revision = "0045_v2_operational_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    document_columns = {row["name"] for row in inspector.get_columns("knowledge_documents")}
    additions = {
        "document_type": sa.Column("document_type", sa.String(64), nullable=False, server_default="sop"),
        "revision": sa.Column("revision", sa.String(64), nullable=False, server_default="1"),
        "effective_from": sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        "effective_to": sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        "asset_ids": sa.Column("asset_ids", sa.JSON(), nullable=False, server_default="[]"),
        "product_codes": sa.Column("product_codes", sa.JSON(), nullable=False, server_default="[]"),
        "process_codes": sa.Column("process_codes", sa.JSON(), nullable=False, server_default="[]"),
        "approved_by_user_id": sa.Column("approved_by_user_id", sa.String(64), nullable=True),
        "approved_at": sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    }
    for name, column in additions.items():
        if name not in document_columns:
            with op.batch_alter_table("knowledge_documents") as batch:
                batch.add_column(column)
    indexes = {row["name"] for row in sa.inspect(bind).get_indexes("knowledge_documents")}
    if "ix_knowledge_documents_document_type" not in indexes:
        op.create_index("ix_knowledge_documents_document_type", "knowledge_documents", ["document_type"])
    chunk_columns = {row["name"] for row in sa.inspect(bind).get_columns("knowledge_chunks")}
    for name, column in {
        "page_reference": sa.Column("page_reference", sa.String(80), nullable=True),
        "section_reference": sa.Column("section_reference", sa.String(180), nullable=True),
    }.items():
        if name not in chunk_columns:
            with op.batch_alter_table("knowledge_chunks") as batch:
                batch.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    chunk_columns = {row["name"] for row in sa.inspect(bind).get_columns("knowledge_chunks")}
    for name in ("section_reference", "page_reference"):
        if name in chunk_columns:
            with op.batch_alter_table("knowledge_chunks") as batch:
                batch.drop_column(name)
    indexes = {row["name"] for row in sa.inspect(bind).get_indexes("knowledge_documents")}
    if "ix_knowledge_documents_document_type" in indexes:
        op.drop_index("ix_knowledge_documents_document_type", table_name="knowledge_documents")
    document_columns = {row["name"] for row in sa.inspect(bind).get_columns("knowledge_documents")}
    for name in ("approved_at", "approved_by_user_id", "process_codes", "product_codes",
                 "asset_ids", "effective_to", "effective_from", "revision", "document_type"):
        if name in document_columns:
            with op.batch_alter_table("knowledge_documents") as batch:
                batch.drop_column(name)
