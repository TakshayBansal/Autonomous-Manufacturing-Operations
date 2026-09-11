"""governed role agents and workspace memberships

Revision ID: 0002_role_agent_os
Revises: 0001_industrial_v1
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

from app.db.models import Base


revision = "0002_role_agent_os"
down_revision = "0001_industrial_v1"
branch_labels = None
depends_on = None


NEW_TABLES = [
    "accounts",
    "workspace_memberships",
    "workspace_invitations",
    "tenant_feature_flags",
    "objectives",
    "agent_threads",
    "agent_messages",
    "agent_runs",
    "agent_tool_calls",
    "agent_proposals",
    "agent_delegations",
    "agent_memories",
    "knowledge_documents",
    "knowledge_chunks",
    "agent_feedback",
]


def table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in column_names(table_name):
        op.add_column(table_name, column)


def create_new_tables() -> None:
    existing = table_names()
    for table_name in NEW_TABLES:
        if table_name in existing:
            continue
        source = Base.metadata.tables[table_name]
        metadata = sa.MetaData()
        table = source.to_metadata(metadata)
        op.create_table(table.name, *list(table.columns), *list(table.constraints))
        existing.add(table_name)


def add_compatibility_columns() -> None:
    add_column_if_missing("tenants", sa.Column("slug", sa.String(120), nullable=True))
    add_column_if_missing("tenants", sa.Column("workspace_kind", sa.String(32), nullable=False, server_default="demo"))
    add_column_if_missing("tenants", sa.Column("onboarding_status", sa.String(48), nullable=False, server_default="complete"))
    add_column_if_missing("tenants", sa.Column("agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_if_missing("tenants", sa.Column("feature_flags", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    # SQLite cannot add a column with a non-constant CURRENT_TIMESTAMP default.
    # ORM inserts always supply this value; existing rows are backfilled below.
    add_column_if_missing("tenants", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

    add_column_if_missing("users", sa.Column("account_id", sa.String(64), nullable=True))

    additions = {
        "agent_profiles": [
            sa.Column("membership_id", sa.String(64), nullable=True),
            sa.Column("prompt_version", sa.String(64), nullable=False, server_default="role-playbook@1"),
            sa.Column("policy_version", sa.String(64), nullable=False, server_default="agent-policy@1"),
            sa.Column("provider", sa.String(48), nullable=False, server_default="groq"),
            sa.Column("model_profile", sa.String(120), nullable=False, server_default="openai/gpt-oss-120b"),
            sa.Column("token_budget", sa.Integer(), nullable=False, server_default="8000"),
            sa.Column("monthly_token_budget", sa.Integer(), nullable=False, server_default="1000000"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("escalation_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        ],
        "tasks": [
            sa.Column("owner_membership_id", sa.String(64), nullable=True),
            sa.Column("parent_task_id", sa.String(64), nullable=True),
            sa.Column("objective_id", sa.String(64), nullable=True),
            sa.Column("delegation_id", sa.String(64), nullable=True),
            sa.Column("creator_membership_id", sa.String(64), nullable=True),
            sa.Column("assignment_source", sa.String(48), nullable=False, server_default="workflow"),
            sa.Column("shared_queue", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("acceptance_status", sa.String(32), nullable=False, server_default="accepted"),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "auth_sessions": [
            sa.Column("account_id", sa.String(64), nullable=True),
            sa.Column("membership_id", sa.String(64), nullable=True),
        ],
    }
    for table_name, columns in additions.items():
        for column in columns:
            add_column_if_missing(table_name, column)


def backfill_memberships() -> None:
    bind = op.get_bind()
    users = bind.execute(sa.text(
        "SELECT id, tenant_id, plant_id, department_id, name, email, role, "
        "password_hash, manager_id FROM users"
    )).mappings().all()
    for user in users:
        account_id = f"acct-{user['id']}"
        membership_id = f"mem-{user['id']}"
        if not bind.execute(sa.text("SELECT 1 FROM accounts WHERE id=:id"), {"id": account_id}).first():
            bind.execute(sa.text(
                "INSERT INTO accounts "
                "(id,email,name,password_hash,status,mfa_enabled,backup_code_hashes,created_at,updated_at) "
                "VALUES (:id,:email,:name,:password_hash,'active',false,:backup_codes,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ), {
                "id": account_id, "email": user["email"], "name": user["name"],
                "password_hash": user["password_hash"], "backup_codes": "[]",
            })
        if not bind.execute(sa.text("SELECT 1 FROM workspace_memberships WHERE id=:id"), {"id": membership_id}).first():
            bind.execute(sa.text(
                "INSERT INTO workspace_memberships "
                "(id,account_id,tenant_id,user_id,default_plant_id,plant_ids,department_id,role,"
                "manager_membership_id,permissions,status,created_at,updated_at) "
                "VALUES (:id,:account_id,:tenant_id,:user_id,:plant_id,:plant_ids,:department_id,:role,"
                ":manager_id,:permissions,'active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ), {
                "id": membership_id, "account_id": account_id, "tenant_id": user["tenant_id"],
                "user_id": user["id"], "plant_id": user["plant_id"],
                "plant_ids": f'["{user["plant_id"]}"]', "department_id": user["department_id"],
                "role": user["role"],
                "manager_id": f"mem-{user['manager_id']}" if user["manager_id"] else None,
                "permissions": "[]",
            })
        bind.execute(sa.text("UPDATE users SET account_id=:account_id WHERE id=:user_id"),
                     {"account_id": account_id, "user_id": user["id"]})
        bind.execute(sa.text(
            "UPDATE tasks SET owner_membership_id=:membership_id "
            "WHERE owner_user_id=:user_id AND owner_membership_id IS NULL"
        ), {"membership_id": membership_id, "user_id": user["id"]})
        bind.execute(sa.text(
            "UPDATE agent_profiles SET membership_id=:membership_id "
            "WHERE user_id=:user_id AND membership_id IS NULL"
        ), {"membership_id": membership_id, "user_id": user["id"]})
    bind.execute(sa.text(
        "UPDATE tenants SET workspace_kind='demo', onboarding_status='complete' "
        "WHERE workspace_kind IS NULL OR workspace_kind=''"
    ))
    bind.execute(sa.text("UPDATE tenants SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL"))


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    create_new_tables()
    add_compatibility_columns()
    backfill_memberships()


def downgrade() -> None:
    for table_name in reversed(NEW_TABLES):
        if table_name in table_names():
            op.drop_table(table_name)
