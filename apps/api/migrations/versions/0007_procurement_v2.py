"""add industry-aligned procurement V2 records and artifact metadata"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.db.models import Base

revision = "0007_procurement_v2"
down_revision = "0006_enable_demo_agents"
branch_labels = None
depends_on = None


def _add(table: str, existing: set[str], column: sa.Column) -> None:
    if column.name not in existing:
        op.add_column(table, column)
        existing.add(column.name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for name in ("material_master_requests", "generated_artifacts", "comparison_approval_requests"):
        if name not in tables:
            source = Base.metadata.tables[name]
            metadata = sa.MetaData()
            table = source.to_metadata(metadata)
            op.create_table(table.name, *list(table.columns), *list(table.constraints), schema=table.schema)
            tables.add(name)

    if "agent_messages" in tables:
        columns = {item["name"] for item in inspector.get_columns("agent_messages")}
        _add("agent_messages", columns, sa.Column("content_format", sa.String(32), nullable=False, server_default="markdown"))
        _add("agent_messages", columns, sa.Column("content_blocks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if "outbox_messages" in tables:
        columns = {item["name"] for item in inspector.get_columns("outbox_messages")}
        _add("outbox_messages", columns, sa.Column("attachment_document_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if "bid_comparisons" in tables:
        columns = {item["name"] for item in inspector.get_columns("bid_comparisons")}
        _add("bid_comparisons", columns, sa.Column("comparison_version", sa.Integer(), nullable=False, server_default="1"))
        _add("bid_comparisons", columns, sa.Column("recommendation_rationale", sa.Text(), nullable=False, server_default=""))
        _add("bid_comparisons", columns, sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        _add("bid_comparisons", columns, sa.Column("submitted_by_user_id", sa.String(64), nullable=True))
    if "gate_entries" in tables:
        columns = {item["name"] for item in inspector.get_columns("gate_entries")}
        _add("gate_entries", columns, sa.Column("supplier_challan", sa.String(120), nullable=False, server_default=""))
        _add("gate_entries", columns, sa.Column("packages_count", sa.Integer(), nullable=False, server_default="0"))
        _add("gate_entries", columns, sa.Column("arrival_notes", sa.Text(), nullable=False, server_default=""))
    if "purchase_requirements" in tables:
        columns = {item["name"] for item in inspector.get_columns("purchase_requirements")}
        _add("purchase_requirements", columns, sa.Column("reason", sa.Text(), nullable=False, server_default=""))

    if "role_definitions" in tables:
        exists = bind.execute(sa.text("SELECT id FROM role_definitions WHERE id='gate_operator'")).first()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO role_definitions "
                    "(id,label,permissions,version,created_at,updated_at) "
                    "VALUES (:id,:label,:permissions,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "gate_operator",
                    "label": "Gate Operator",
                    "permissions": '["record_gate_entry","read_purchase_orders"]',
                },
            )

    if "tasks" in tables:
        bind.execute(
            sa.text(
                "UPDATE tasks SET owner_role='purchase_manager', "
                "owner_user_id=(SELECT m.user_id FROM workspace_memberships m "
                "WHERE m.tenant_id=tasks.tenant_id AND m.default_plant_id=tasks.plant_id "
                "AND m.role='purchase_manager' AND m.status='active' LIMIT 1), "
                "owner_membership_id=(SELECT m.id FROM workspace_memberships m "
                "WHERE m.tenant_id=tasks.tenant_id AND m.default_plant_id=tasks.plant_id "
                "AND m.role='purchase_manager' AND m.status='active' LIMIT 1), "
                "shared_queue=CASE WHEN EXISTS (SELECT 1 FROM workspace_memberships m "
                "WHERE m.tenant_id=tasks.tenant_id AND m.default_plant_id=tasks.plant_id "
                "AND m.role='purchase_manager' AND m.status='active') THEN false ELSE true END "
                "WHERE status IN ('pending','open','in_progress') "
                "AND entity_type IN ('supplier_quote','supplier_quotes','bid_comparison','bid_comparisons')"
            )
        )

    if "tenant_feature_flags" in tables and "tenants" in tables:
        tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenants"))]
        for tenant_id in tenant_ids:
            exists = bind.execute(
                sa.text(
                    "SELECT id FROM tenant_feature_flags "
                    "WHERE tenant_id=:tenant_id AND key='procurement_v2'"
                ),
                {"tenant_id": tenant_id},
            ).first()
            if not exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO tenant_feature_flags "
                        "(id,tenant_id,key,enabled,config,updated_at) "
                        "VALUES (:id,:tenant_id,'procurement_v2',true,:config,CURRENT_TIMESTAMP)"
                    ),
                    {"id": str(uuid4()), "tenant_id": tenant_id, "config": "{}"},
                )


def downgrade() -> None:
    # Approval and artifact history is retained deliberately.
    pass
