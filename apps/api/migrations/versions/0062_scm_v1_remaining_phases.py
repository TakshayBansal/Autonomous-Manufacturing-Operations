"""SCM V1 remaining phases.

Revision ID: 0062_scm_v1_remaining_phases
Revises: 0061_scm_phases_0_3
"""
from alembic import op
import sqlalchemy as sa
from app.db.models import Base

revision = "0062_scm_v1_remaining_phases"
down_revision = "0061_scm_phases_0_3"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    scenario_columns = [sa.Column("baseline_run_id", sa.String(64), nullable=True),
        sa.Column("result_run_id", sa.String(64), nullable=True),
        sa.Column("duplicated_from_id", sa.String(64), nullable=True), sa.Column("description", sa.Text(), nullable=True)]
    recommendation_columns = [sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Numeric(20, 6), nullable=True),
        sa.Column("score_dimensions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("estimated_impact", sa.JSON(), nullable=False, server_default="{}")]
    for table, columns in (("scm_planning_scenarios", scenario_columns), ("scm_recommendations", recommendation_columns)):
        existing = {item["name"] for item in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    for name in ("scm_recommendation_simulations", "scm_saved_views", "scm_planner_notes"):
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    op.drop_table("scm_planner_notes")
    op.drop_table("scm_saved_views")
    op.drop_table("scm_recommendation_simulations")
    with op.batch_alter_table("scm_recommendations") as batch:
        for name in ("estimated_impact", "score_dimensions", "score", "rank"):
            batch.drop_column(name)
    with op.batch_alter_table("scm_planning_scenarios") as batch:
        for name in ("description", "duplicated_from_id", "result_run_id", "baseline_run_id"):
            batch.drop_column(name)
