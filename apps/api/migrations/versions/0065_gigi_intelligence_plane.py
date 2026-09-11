"""Gigi shared intelligence-plane persistence.

Revision ID: 0065_gigi_intelligence
Revises: 0064_scm_manual_entries
"""
from alembic import op
import sqlalchemy as sa

revision = "0065_gigi_intelligence"
down_revision = "0064_scm_manual_entries"
branch_labels = None
depends_on = None


def _column(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if table in inspector.get_table_names() and column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    _column("agent_threads", sa.Column("module_context", sa.String(48), nullable=True))
    _column("agent_threads", sa.Column("conversation_metadata", sa.JSON(), nullable=False, server_default="{}"))
    _column("agent_threads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    _column("agent_messages", sa.Column("run_id", sa.String(64), nullable=True))
    for column in (
        sa.Column("run_type", sa.String(48), nullable=False, server_default="conversation"),
        sa.Column("role_profile", sa.String(64), nullable=False, server_default="operator"),
        sa.Column("prompt_version", sa.String(80), nullable=False, server_default="gigi-core@1"),
        sa.Column("model_task_class", sa.String(32), nullable=False, server_default="REASONING"),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    ): _column("agent_runs", column)
    for column in (
        sa.Column("tool_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("call_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    ): _column("agent_tool_calls", column)
    for column in (
        sa.Column("memory_type", sa.String(48), nullable=False, server_default="preference"),
        sa.Column("scope_type", sa.String(48), nullable=False, server_default="user"),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("validation_state", sa.String(32), nullable=False, server_default="verified"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    ): _column("agent_memories", column)
    _column("knowledge_documents", sa.Column("checksum", sa.String(64), nullable=True))
    _column("knowledge_documents", sa.Column("authoritative_source", sa.String(240), nullable=True))
    _column("knowledge_chunks", sa.Column("search_text", sa.Text(), nullable=True))
    _column("agent_feedback", sa.Column("message_id", sa.String(64), nullable=True))
    _column("agent_feedback", sa.Column("experience_id", sa.String(64), nullable=True))
    _column("agent_feedback", sa.Column("feedback_type", sa.String(48), nullable=False, server_default="response"))

    def common():
        return [sa.Column("id", sa.String(64), primary_key=True), sa.Column("public_id", sa.String(36), nullable=False, unique=True),
            sa.Column("business_number", sa.String(80), nullable=True), sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    definitions = {
        "ai_prompt_versions": [sa.Column("name", sa.String(120), nullable=False), sa.Column("version_label", sa.String(48), nullable=False), sa.Column("task_class", sa.String(32), nullable=False), sa.Column("template_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), *common(), sa.UniqueConstraint("tenant_id", "name", "version_label", name="uq_ai_prompt_version")],
        "ai_investigations": [sa.Column("trigger_type", sa.String(120), nullable=False), sa.Column("trigger_reference", sa.String(160), nullable=False), sa.Column("entity_type", sa.String(80)), sa.Column("entity_id", sa.String(64)), sa.Column("severity", sa.String(24), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("dedupe_key", sa.String(180), nullable=False), sa.Column("run_id", sa.String(64)), sa.Column("findings", sa.JSON(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("correlation_id", sa.String(80), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), *common(), sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_ai_investigation_dedupe")],
        "ai_briefings": [sa.Column("membership_id", sa.String(64), nullable=False), sa.Column("briefing_type", sa.String(48), nullable=False), sa.Column("period_key", sa.String(80), nullable=False), sa.Column("title", sa.String(240), nullable=False), sa.Column("items", sa.JSON(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("viewed_at", sa.DateTime(timezone=True)), sa.Column("dismissed_at", sa.DateTime(timezone=True)), *common(), sa.UniqueConstraint("tenant_id", "membership_id", "briefing_type", "period_key", name="uq_ai_briefing_period")],
        "agent_experiences": [sa.Column("domain", sa.String(48), nullable=False), sa.Column("problem_type", sa.String(80), nullable=False), sa.Column("problem_signature", sa.String(160), nullable=False), sa.Column("entity_type", sa.String(80)), sa.Column("entity_id", sa.String(64)), sa.Column("action_intent_id", sa.String(64)), sa.Column("context_reference", sa.JSON(), nullable=False), sa.Column("candidates", sa.JSON(), nullable=False), sa.Column("selected_strategy", sa.JSON(), nullable=False), sa.Column("predicted_outcome", sa.JSON(), nullable=False), sa.Column("actual_outcome", sa.JSON(), nullable=False), sa.Column("effectiveness", sa.Float()), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False), *common()],
        "knowledge_document_entity_links": [sa.Column("knowledge_document_id", sa.String(64), nullable=False), sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", sa.String(64), nullable=False), sa.Column("relationship", sa.String(48), nullable=False), *common(), sa.UniqueConstraint("knowledge_document_id", "entity_type", "entity_id", name="uq_knowledge_document_entity")],
    }
    for table, columns in definitions.items():
        if table not in tables:
            op.create_table(table, *columns)
            op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def downgrade() -> None:
    for table in ("knowledge_document_entity_links", "agent_experiences", "ai_briefings", "ai_investigations", "ai_prompt_versions"):
        op.drop_table(table)
