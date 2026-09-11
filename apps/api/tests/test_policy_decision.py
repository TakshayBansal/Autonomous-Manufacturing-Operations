from app.db import models
from app.db.session import SessionLocal
from app.policy_decision import PolicyDecisionService, simulate_template
from app import policy_bundles


def membership() -> models.WorkspaceMembership:
    return models.WorkspaceMembership(id="policy-member", account_id="policy-account", tenant_id="policy-tenant",
        user_id="policy-user", default_plant_id="policy-plant", plant_ids=["policy-plant"],
        department_id="purchase", role="purchase_manager", permissions=[], status="active")


def test_opa_unavailable_defaults_mutations_to_deny_and_reads_to_allow() -> None:
    with SessionLocal() as db:
        actor = membership()
        mutation, _ = PolicyDecisionService(db).decide(actor=actor, capability_id="delegate_task",
            resource_type="task", resource_id="task-1", context={"tenant_id": actor.tenant_id},
            read_only=False, correlation_id="policy-test-mutation")
        read, _ = PolicyDecisionService(db).decide(actor=actor, capability_id="list_my_tasks",
            resource_type="task", resource_id=None, context={"tenant_id": actor.tenant_id},
            read_only=True, correlation_id="policy-test-read")
        assert mutation.allow is False
        assert mutation.reason_code == "opa_unavailable_default_deny"
        assert read.allow is True


def test_safe_policy_template_simulation_enforces_scope_limits_and_confirmation() -> None:
    policy = models.AutonomyPolicy(id="policy-1", tenant_id="tenant", plant_id="plant", name="Coordination",
        capability_id="delegate_task", roles=["purchase_manager"], plant_ids=["plant"], category_ids=[],
        autonomy_ceiling=2, spend_limit=1000, risk_limit="medium", external_communication="confirm",
        confirmation_required=False, state="published", policy_version="policy-1@1")
    allowed = simulate_template(policy, role="purchase_manager", plant_id="plant", capability_id="delegate_task",
        spend=900, risk="low", external_effect=True)
    denied = simulate_template(policy, role="purchase_manager", plant_id="plant", capability_id="delegate_task",
        spend=1200, risk="low")
    assert allowed.allow and allowed.requires_confirmation and allowed.autonomy_tier == 2
    assert denied.allow is False


def test_signed_policy_bundle_can_be_verified_and_reactivated() -> None:
    with SessionLocal() as db:
        policy = models.AutonomyPolicy(id="bundle-policy", tenant_id="bundle-tenant", plant_id="bundle-plant",
            name="Bundle policy", capability_id="delegate_task", roles=["purchase_manager"], plant_ids=[],
            category_ids=[], autonomy_ceiling=2, risk_limit="low", external_communication="confirm",
            confirmation_required=True, state="published", policy_version="bundle-policy@1")
        db.add(policy)
        db.flush()
        bundle = policy_bundles.build(db, "bundle-tenant", "bundle-plant", "bundle-admin")
        db.flush()
        bundle.state = "retired"
        assert policy_bundles.activate(db, bundle).state == "active"
        bundle.signature = "tampered"
        try:
            policy_bundles.activate(db, bundle)
        except ValueError as exc:
            assert "signature" in str(exc)
        else:
            raise AssertionError("Tampered bundle was accepted")
