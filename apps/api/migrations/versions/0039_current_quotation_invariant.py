"""Repair quotation revisions and protect the single-current invariant."""

from alembic import op
import sqlalchemy as sa


revision = "0039_current_quotation_invariant"
down_revision = "0038_quotation_intakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "supplier_quotes" not in inspector.get_table_names():
        return
    metadata = sa.MetaData()
    quotes = sa.Table("supplier_quotes", metadata, autoload_with=bind)
    tasks = sa.Table("tasks", metadata, autoload_with=bind) if "tasks" in inspector.get_table_names() else None
    rows = bind.execute(sa.select(quotes).where(quotes.c.verification_status != "superseded")).mappings().all()
    groups: dict[tuple[str, str | None, str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["tenant_id"], row.get("plant_id"), row["rfq_id"], row["supplier_id"]), []).append(dict(row))
    for group in groups.values():
        if len(group) < 2:
            continue
        # Verified evidence, explicit revision, creation time, then stable ID.
        group.sort(key=lambda row: (
            row.get("verification_status") == "verified",
            int(row.get("revision_number") or 1),
            row.get("created_at"), row["id"],
        ), reverse=True)
        canonical = group[0]
        for old in group[1:]:
            bind.execute(quotes.update().where(quotes.c.id == old["id"]).values(
                verification_status="superseded",
            ))
            if canonical.get("supersedes_quote_id") is None:
                bind.execute(quotes.update().where(quotes.c.id == canonical["id"]).values(
                    supersedes_quote_id=old["id"],
                ))
            if tasks is not None:
                bind.execute(tasks.update().where(
                    tasks.c.entity_type == "supplier_quotes", tasks.c.entity_id == old["id"],
                    tasks.c.status.in_(["open", "accepted", "in_progress", "review", "pending_approval"]),
                ).values(status="completed"))
    existing = {index["name"] for index in inspector.get_indexes("supplier_quotes")}
    if "uq_supplier_quote_current_revision" not in existing:
        op.create_index(
            "uq_supplier_quote_current_revision", "supplier_quotes",
            ["tenant_id", "plant_id", "rfq_id", "supplier_id"], unique=True,
            postgresql_where=sa.text("verification_status <> 'superseded'"),
            sqlite_where=sa.text("verification_status <> 'superseded'"),
        )


def downgrade() -> None:
    op.drop_index("uq_supplier_quote_current_revision", table_name="supplier_quotes")
