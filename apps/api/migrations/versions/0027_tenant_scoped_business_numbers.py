"""Scope business-number uniqueness to the tenant."""
from alembic import op
import sqlalchemy as sa

revision = "0027_tenant_scoped_business_numbers"
down_revision = "0026_retention_holds"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns(table)}
        if not {"tenant_id", "business_number"}.issubset(columns):
            continue
        unique_constraints = inspector.get_unique_constraints(table)
        global_business_number = [
            constraint for constraint in unique_constraints
            if constraint.get("column_names") == ["business_number"]
        ]
        composite_exists = any(
            set(constraint.get("column_names") or []) == {"tenant_id", "business_number"}
            for constraint in unique_constraints
        )
        with op.batch_alter_table(table, naming_convention=NAMING_CONVENTION) as batch:
            for constraint in global_business_number:
                name = constraint.get("name") or f"uq_{table}_business_number"
                batch.drop_constraint(name, type_="unique")
            if not composite_exists:
                batch.create_unique_constraint(
                    f"uq_{table}_tenant_business_number",
                    ["tenant_id", "business_number"],
                )


def downgrade():
    # Restoring global uniqueness can fail after multiple tenants legitimately
    # use the same business reference. Production rollback is forward-fix only.
    pass
