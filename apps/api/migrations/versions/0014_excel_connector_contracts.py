"""Add first-class spreadsheet connector contracts and lineage."""

from alembic import op
import sqlalchemy as sa


revision = "0014_excel_connector_contracts"
down_revision = "0013_coordination_idempotency"
branch_labels = None
depends_on = None


SCOPED = [
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("public_id", sa.String(36), nullable=False, unique=True),
    sa.Column("business_number", sa.String(80), nullable=True, unique=True),
    sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
    sa.Column("plant_id", sa.String(64), nullable=True, index=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
]


def _table(name: str, *columns: sa.Column, constraints: sa.Constraint | None = None) -> None:
    args = [column.copy() for column in SCOPED] + list(columns)
    if constraints is not None:
        args.append(constraints)
    op.create_table(name, *args)


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "connector_definitions" not in existing:
        _table("connector_definitions",
            sa.Column("connector_type", sa.String(80), nullable=False), sa.Column("display_name", sa.String(160), nullable=False),
            sa.Column("manifest_version", sa.String(32), nullable=False), sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            constraints=sa.UniqueConstraint("tenant_id", "connector_type", "manifest_version", name="uq_connector_definition_version"))
    if "integration_mapping_profiles" not in existing:
        _table("integration_mapping_profiles",
            sa.Column("connection_id", sa.String(64), sa.ForeignKey("integration_connections.id"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False), sa.Column("profile_version", sa.Integer(), nullable=False),
            sa.Column("workbook_schema_version", sa.String(32), nullable=False), sa.Column("mappings", sa.JSON(), nullable=False),
            sa.Column("transforms", sa.JSON(), nullable=False), sa.Column("ownership", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            constraints=sa.UniqueConstraint("connection_id", "name", "profile_version", name="uq_mapping_profile_version"))
    if "integration_import_batches" not in existing:
        _table("integration_import_batches",
            sa.Column("connection_id", sa.String(64), sa.ForeignKey("integration_connections.id"), nullable=False),
            sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=True),
            sa.Column("mapping_profile_id", sa.String(64), sa.ForeignKey("integration_mapping_profiles.id"), nullable=True),
            sa.Column("source_filename", sa.String(240), nullable=False), sa.Column("source_hash", sa.String(64), nullable=False),
            sa.Column("workbook_version", sa.String(80), nullable=False), sa.Column("mode", sa.String(32), nullable=False),
            sa.Column("status", sa.String(48), nullable=False), sa.Column("discovery", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False), sa.Column("approved_by_user_id", sa.String(64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), sa.Column("correlation_id", sa.String(80), nullable=False))
    if "integration_import_row_results" not in existing:
        _table("integration_import_row_results",
            sa.Column("batch_id", sa.String(64), sa.ForeignKey("integration_import_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sheet_name", sa.String(160), nullable=False), sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("external_key", sa.String(240), nullable=True), sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("action", sa.String(32), nullable=False), sa.Column("canonical_entity_type", sa.String(80), nullable=True),
            sa.Column("canonical_entity_id", sa.String(64), nullable=True), sa.Column("validation_messages", sa.JSON(), nullable=False),
            sa.Column("source_cells", sa.JSON(), nullable=False), sa.Column("mapping_version", sa.String(32), nullable=False),
            sa.Column("correlation_id", sa.String(80), nullable=False),
            constraints=sa.UniqueConstraint("batch_id", "sheet_name", "row_number", name="uq_import_batch_source_row"))
    if "integration_export_batches" not in existing:
        _table("integration_export_batches",
            sa.Column("connection_id", sa.String(64), sa.ForeignKey("integration_connections.id"), nullable=False),
            sa.Column("source_document_id", sa.String(64), nullable=True), sa.Column("output_document_id", sa.String(64), nullable=True),
            sa.Column("export_type", sa.String(64), nullable=False), sa.Column("status", sa.String(48), nullable=False),
            sa.Column("output_version", sa.Integer(), nullable=False), sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False), sa.Column("correlation_id", sa.String(80), nullable=False))
    if "integration_external_record_states" not in existing:
        _table("integration_external_record_states",
            sa.Column("connection_id", sa.String(64), sa.ForeignKey("integration_connections.id"), nullable=False),
            sa.Column("external_entity_type", sa.String(80), nullable=False), sa.Column("external_key", sa.String(240), nullable=False),
            sa.Column("canonical_entity_type", sa.String(80), nullable=True), sa.Column("canonical_entity_id", sa.String(64), nullable=True),
            sa.Column("external_payload_hash", sa.String(64), nullable=False), sa.Column("external_version", sa.String(80), nullable=True),
            sa.Column("canonical_version", sa.Integer(), nullable=True), sa.Column("ownership", sa.String(32), nullable=False),
            sa.Column("sync_status", sa.String(48), nullable=False), sa.Column("tombstoned", sa.Boolean(), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            constraints=sa.UniqueConstraint("connection_id", "external_entity_type", "external_key", name="uq_connection_external_record"))


def downgrade() -> None:
    for table in ("integration_external_record_states", "integration_export_batches", "integration_import_row_results", "integration_import_batches", "integration_mapping_profiles", "connector_definitions"):
        op.drop_table(table)
