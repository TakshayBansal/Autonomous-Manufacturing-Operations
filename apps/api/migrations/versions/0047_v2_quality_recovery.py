"""Add SPC evidence and governed NCR/CAPA recovery records."""
from alembic import op
import sqlalchemy as sa

revision = "0047_v2_quality_recovery"
down_revision = "0046_v2_knowledge_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    quality_columns = {row["name"] for row in inspector.get_columns("production_quality_events")}
    additions = {
        "event_type": sa.Column("event_type", sa.String(32), nullable=False, server_default="inspection"),
        "asset_id": sa.Column("asset_id", sa.String(64), nullable=True),
        "material_lot_id": sa.Column("material_lot_id", sa.String(120), nullable=True),
        "measurement_name": sa.Column("measurement_name", sa.String(120), nullable=True),
        "measurement_value": sa.Column("measurement_value", sa.Float(), nullable=True),
        "lower_control_limit": sa.Column("lower_control_limit", sa.Float(), nullable=True),
        "upper_control_limit": sa.Column("upper_control_limit", sa.Float(), nullable=True),
        "severity": sa.Column("severity", sa.String(24), nullable=True),
        "evidence": sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
    }
    for name, column in additions.items():
        if name not in quality_columns:
            with op.batch_alter_table("production_quality_events") as batch:
                batch.add_column(column)

    inspector = sa.inspect(bind)
    quality_indexes = {row["name"] for row in inspector.get_indexes("production_quality_events")}
    for name, columns in {
        "ix_production_quality_events_event_type": ["event_type"],
        "ix_production_quality_events_asset_id": ["asset_id"],
        "ix_production_quality_events_material_lot_id": ["material_lot_id"],
    }.items():
        if name not in quality_indexes:
            op.create_index(name, "production_quality_events", columns)

    if "quality_recovery_cases" not in inspector.get_table_names():
        op.create_table(
            "quality_recovery_cases",
            sa.Column("case_type", sa.String(24), nullable=False),
            sa.Column("parent_case_id", sa.String(64), nullable=True),
            sa.Column("quality_event_id", sa.String(64), nullable=True),
            sa.Column("deviation_id", sa.String(64), nullable=True),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="open"),
            sa.Column("severity", sa.String(24), nullable=False, server_default="medium"),
            sa.Column("owner_user_id", sa.String(64), nullable=True),
            sa.Column("problem_statement", sa.Text(), nullable=False),
            sa.Column("containment_summary", sa.Text(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("corrective_action", sa.Text(), nullable=True),
            sa.Column("effectiveness_criteria", sa.Text(), nullable=True),
            sa.Column("effectiveness_result", sa.Text(), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by_user_id", sa.String(64), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("public_id", sa.String(36), nullable=False, unique=True),
            sa.Column("business_number", sa.String(80), nullable=True),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("plant_id", sa.String(64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["parent_case_id"], ["quality_recovery_cases.id"]),
            sa.ForeignKeyConstraint(["quality_event_id"], ["production_quality_events.id"]),
            sa.ForeignKeyConstraint(["deviation_id"], ["operational_deviations.id"]),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        )
    inspector = sa.inspect(bind)
    case_indexes = {row["name"] for row in inspector.get_indexes("quality_recovery_cases")}
    for name, columns in {
        "ix_quality_recovery_cases_public_id": ["public_id"],
        "ix_quality_recovery_cases_business_number": ["business_number"],
        "ix_quality_recovery_cases_tenant_id": ["tenant_id"],
        "ix_quality_recovery_cases_plant_id": ["plant_id"],
        "ix_quality_recovery_cases_case_type": ["case_type"],
        "ix_quality_recovery_cases_parent_case_id": ["parent_case_id"],
        "ix_quality_recovery_cases_quality_event_id": ["quality_event_id"],
        "ix_quality_recovery_cases_deviation_id": ["deviation_id"],
        "ix_quality_recovery_cases_status": ["status"],
        "ix_quality_recovery_cases_owner_user_id": ["owner_user_id"],
        "ix_quality_recovery_cases_due_at": ["due_at"],
    }.items():
        if name not in case_indexes:
            op.create_index(name, "quality_recovery_cases", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "quality_recovery_cases" in inspector.get_table_names():
        op.drop_table("quality_recovery_cases")
    quality_indexes = {row["name"] for row in sa.inspect(bind).get_indexes("production_quality_events")}
    for name in ("ix_production_quality_events_material_lot_id", "ix_production_quality_events_asset_id",
                 "ix_production_quality_events_event_type"):
        if name in quality_indexes:
            op.drop_index(name, table_name="production_quality_events")
    quality_columns = {row["name"] for row in sa.inspect(bind).get_columns("production_quality_events")}
    for name in ("evidence", "severity", "upper_control_limit", "lower_control_limit",
                 "measurement_value", "measurement_name", "material_lot_id", "asset_id", "event_type"):
        if name in quality_columns:
            with op.batch_alter_table("production_quality_events") as batch:
                batch.drop_column(name)
