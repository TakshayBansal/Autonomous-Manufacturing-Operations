"""V2 plant intelligence and production recovery core."""
from alembic import op

from app.db.models import Base

revision = "0045_v2_operational_core"
down_revision = "0044_proactive_companion"
branch_labels = None
depends_on = None

TABLES = (
    "plant_areas", "production_lines", "plant_assets", "plant_shifts",
    "production_work_orders", "production_plan_points", "production_actual_points",
    "production_downtime_events", "production_quality_events", "asset_fault_events",
    "production_material_requirements", "material_inventory_positions",
    "production_supplier_commitments", "material_readiness_snapshots",
    "operational_deviations", "quality_containment_records", "maintenance_work_records",
    "operational_actions",
    "operational_evidence_refs", "operational_value_entries",
    "improvement_experiments", "improvement_benefit_measurements",
    "shift_briefings",
    "operational_setup_profiles", "edge_gateways", "edge_source_mappings",
    "edge_source_health", "edge_ingest_receipts",
    "v2_prepared_actions",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
