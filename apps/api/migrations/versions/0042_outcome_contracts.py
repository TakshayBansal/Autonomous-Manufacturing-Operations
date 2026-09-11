"""Immutable commitment revisions and explicit delegation outcome contracts."""
from alembic import op
import sqlalchemy as sa

revision = "0042_outcome_contracts"
down_revision = "0041_governed_execution_runtime"
branch_labels = None
depends_on = None

def _columns(table: str) -> set[str]:
    return {row["name"] for row in sa.inspect(op.get_bind()).get_columns(table)}

def upgrade() -> None:
    if "supersedes_commitment_id" not in _columns("commitments"):
        with op.batch_alter_table("commitments") as batch:
            batch.add_column(sa.Column("supersedes_commitment_id", sa.String(64)))
            batch.create_index("ix_commitments_supersedes_commitment_id", ["supersedes_commitment_id"])
    existing = _columns("agent_delegations")
    fields = (
        ("contract_kind", sa.String(32)), ("expected_deliverable", sa.Text),
        ("required_evidence", sa.JSON), ("constraints", sa.JSON),
        ("accountability_membership_id", sa.String(64)), ("acceptance_status", sa.String(32)),
        ("accepted_at", sa.DateTime(timezone=True)),
    )
    missing = [(name, kind) for name, kind in fields if name not in existing]
    if missing:
        with op.batch_alter_table("agent_delegations") as batch:
            for name, kind in missing:
                batch.add_column(sa.Column(name, kind))

def downgrade() -> None:
    with op.batch_alter_table("agent_delegations") as batch:
        for name in ("accepted_at", "acceptance_status", "accountability_membership_id", "constraints", "required_evidence", "expected_deliverable", "contract_kind"):
            batch.drop_column(name)
    with op.batch_alter_table("commitments") as batch:
        batch.drop_index("ix_commitments_supersedes_commitment_id")
        batch.drop_column("supersedes_commitment_id")
