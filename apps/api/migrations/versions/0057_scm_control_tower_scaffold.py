"""SCM control-tower canonical model and planning read models.

Revision ID: 0057_scm_control_tower_scaffold
Revises: 0056_v2_1_recovery_intelligence
"""
from alembic import op

from app.db.models import Base

revision = "0057_scm_control_tower_scaffold"
down_revision = "0056_v2_1_recovery_intelligence"
branch_labels = None
depends_on = None


TABLE_NAMES = [
    "scm_materials",
    "scm_material_plants",
    "scm_storage_locations",
    "scm_material_plant_policies",
    "scm_uom_conversions",
    "scm_material_suppliers",
    "scm_customers",
    "scm_material_customer_usage",
    "scm_boms",
    "scm_bom_lines",
    "scm_inventory_snapshots",
    "scm_demand_forecasts",
    "scm_material_requirements",
    "scm_supply_orders",
    "scm_supply_schedule_lines",
    "scm_goods_receipts",
    "scm_data_source_states",
    "scm_planning_policy_sets",
    "scm_planning_scenarios",
    "scm_scenario_overrides",
    "scm_planning_adjustments",
    "scm_planning_runs",
    "scm_planning_events",
    "scm_material_projection_points",
    "scm_supply_demand_pegs",
    "scm_material_risk_summaries",
    "scm_recommendations",
]


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLE_NAMES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)

