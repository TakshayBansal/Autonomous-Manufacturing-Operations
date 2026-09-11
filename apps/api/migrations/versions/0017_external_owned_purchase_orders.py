"""Allow externally owned purchase orders without a local award record."""
from alembic import op
import sqlalchemy as sa

revision = "0017_external_owned_purchase_orders"
down_revision = "0016_invoice_matching"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Alembic's historical default version column is VARCHAR(32), while this
    # and later descriptive revision identifiers are longer. PostgreSQL
    # enforces that limit when Alembic records this revision after upgrade();
    # SQLite does not, which is why disposable SQLite migrations did not expose
    # the deployment failure. Widen before Alembic advances version_num.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
    columns = {row["name"]: row for row in sa.inspect(op.get_bind()).get_columns("po_drafts")}
    if not columns["award_id"].get("nullable", True):
        with op.batch_alter_table("po_drafts") as batch:
            batch.alter_column("award_id", existing_type=sa.String(64), nullable=True)

def downgrade() -> None:
    # Existing externally owned orders must be reconciled before making this
    # field mandatory; intentionally no destructive downgrade.
    pass
