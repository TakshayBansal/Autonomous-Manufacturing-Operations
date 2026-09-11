"""Add plant timezone, currency and locale presentation contract."""
from alembic import op
import sqlalchemy as sa

revision = "0049_v2_plant_locale"
down_revision = "0048_v2_multi_plant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {row["name"] for row in sa.inspect(bind).get_columns("plants")}
    for name, column in {
        "timezone": sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        "currency": sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        "locale": sa.Column("locale", sa.String(32), nullable=False, server_default="en-US"),
        "status": sa.Column("status", sa.String(24), nullable=False, server_default="active"),
    }.items():
        if name not in columns:
            with op.batch_alter_table("plants") as batch:
                batch.add_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    columns = {row["name"] for row in sa.inspect(bind).get_columns("plants")}
    for name in ("status", "locale", "currency", "timezone"):
        if name in columns:
            with op.batch_alter_table("plants") as batch:
                batch.drop_column(name)
