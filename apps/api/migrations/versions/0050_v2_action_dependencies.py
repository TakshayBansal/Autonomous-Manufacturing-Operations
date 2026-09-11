"""Add cross-functional operational action dependencies.

Revision ID: 0050_v2_action_dependencies
Revises: 0049_v2_plant_locale
"""

from alembic import op
import sqlalchemy as sa

revision = "0050_v2_action_dependencies"
down_revision = "0049_v2_plant_locale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "operational_action_dependencies" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "operational_action_dependencies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False, unique=True),
        sa.Column("business_number", sa.String(80), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action_id", sa.String(64), sa.ForeignKey("operational_actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predecessor_action_id", sa.String(64), sa.ForeignKey("operational_actions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dependency_type", sa.String(48), nullable=False, server_default="finish_to_start"),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("owner_role", sa.String(64), nullable=True),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_required", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("action_id", "title", name="uq_operational_action_dependency"),
    )
    for column in ("tenant_id", "plant_id", "action_id", "predecessor_action_id", "status"):
        op.create_index(f"ix_operational_action_dependencies_{column}", "operational_action_dependencies", [column])
    op.create_index(
        "ix_operational_action_dependencies_public_id",
        "operational_action_dependencies",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_operational_action_dependencies_business_number",
        "operational_action_dependencies",
        ["business_number"],
    )


def downgrade() -> None:
    if "operational_action_dependencies" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("operational_action_dependencies")
