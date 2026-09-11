"""Add standardized KPI governance and cross-site practice transfers."""
from alembic import op
import sqlalchemy as sa

revision = "0048_v2_multi_plant"
down_revision = "0047_v2_quality_recovery"
branch_labels = None
depends_on = None


SCOPED = [
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("public_id", sa.String(36), nullable=False, unique=True),
    sa.Column("business_number", sa.String(80), nullable=True),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("plant_id", sa.String(64), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "standard_kpi_definitions" not in tables:
        op.create_table(
            "standard_kpi_definitions",
            sa.Column("key", sa.String(120), nullable=False),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("unit", sa.String(48), nullable=False),
            sa.Column("formula", sa.Text(), nullable=False),
            sa.Column("direction", sa.String(24), nullable=False, server_default="higher_is_better"),
            sa.Column("context_dimensions", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("version_label", sa.String(48), nullable=False, server_default="1.0"),
            sa.Column("status", sa.String(24), nullable=False, server_default="active"),
            sa.Column("approved_by_user_id", sa.String(64), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            *SCOPED,
            sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
            sa.UniqueConstraint("tenant_id", "key", "version_label", name="uq_standard_kpi_version"),
        )
    if "best_practice_transfers" not in tables:
        op.create_table(
            "best_practice_transfers",
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("source_plant_id", sa.String(64), nullable=False),
            sa.Column("target_plant_id", sa.String(64), nullable=False),
            sa.Column("source_experiment_id", sa.String(64), nullable=True),
            sa.Column("source_deviation_pattern", sa.String(120), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
            sa.Column("hypothesis", sa.Text(), nullable=False),
            sa.Column("applicability_context", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("expected_benefit", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("owner_user_id", sa.String(64), nullable=True),
            sa.Column("accepted_by_user_id", sa.String(64), nullable=True),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
            *[column._copy() for column in SCOPED],
            sa.ForeignKeyConstraint(["source_plant_id"], ["plants.id"]),
            sa.ForeignKeyConstraint(["target_plant_id"], ["plants.id"]),
            sa.ForeignKeyConstraint(["source_experiment_id"], ["improvement_experiments.id"]),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        )
    for table, definitions in {
        "standard_kpi_definitions": {"key": ["key"], "status": ["status"]},
        "best_practice_transfers": {"source_plant_id": ["source_plant_id"], "target_plant_id": ["target_plant_id"], "status": ["status"]},
    }.items():
        existing = {row["name"] for row in sa.inspect(bind).get_indexes(table)}
        for suffix, columns in definitions.items():
            name = f"ix_{table}_{suffix}"
            if name not in existing:
                op.create_index(name, table, columns)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "best_practice_transfers" in tables:
        op.drop_table("best_practice_transfers")
    if "standard_kpi_definitions" in tables:
        op.drop_table("standard_kpi_definitions")
