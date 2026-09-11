"""Link domain cases to shared cases. Revision ID: 0074_domain_case_links"""
from alembic import op
import sqlalchemy as sa
revision="0074_domain_case_links"; down_revision="0073_case_execution_core"; branch_labels=None; depends_on=None
def upgrade():
    inspector=sa.inspect(op.get_bind())
    for table in ("cases","recovery_cases"):
        if "operational_case_id" not in {row["name"] for row in inspector.get_columns(table)}:
            op.add_column(table,sa.Column("operational_case_id",sa.String(64),nullable=True)); op.create_index(f"ix_{table}_operational_case_id",table,["operational_case_id"])
def downgrade():
    for table in ("recovery_cases","cases"):
        op.drop_index(f"ix_{table}_operational_case_id",table_name=table); op.drop_column(table,"operational_case_id")
