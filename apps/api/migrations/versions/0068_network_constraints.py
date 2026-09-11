"""Network constraints contract. Revision ID: 0068_network_constraints"""
from alembic import op
import sqlalchemy as sa
revision="0068_network_constraints"; down_revision="0067_case_exposure"; branch_labels=None; depends_on=None
def upgrade():
 if "platform_network_constraints" in set(sa.inspect(op.get_bind()).get_table_names()): return
 op.create_table("platform_network_constraints",sa.Column("id",sa.String(64),primary_key=True),sa.Column("public_id",sa.String(36),nullable=False,unique=True),sa.Column("business_number",sa.String(80)),sa.Column("tenant_id",sa.String(64),nullable=False),sa.Column("plant_id",sa.String(64)),sa.Column("version",sa.Integer(),nullable=False,server_default="1"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("constraint_type",sa.String(80),nullable=False),sa.Column("subject_type",sa.String(80),nullable=False),sa.Column("subject_id",sa.String(64),nullable=False),sa.Column("values",sa.JSON(),nullable=False),sa.Column("source",sa.String(120),nullable=False),sa.Column("provenance",sa.JSON(),nullable=False),sa.Column("valid_from",sa.DateTime(timezone=True)),sa.Column("valid_to",sa.DateTime(timezone=True)),sa.Column("observed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("freshness_policy",sa.JSON(),nullable=False))
def downgrade(): op.drop_table("platform_network_constraints")
