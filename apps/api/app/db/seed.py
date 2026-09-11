from datetime import datetime, timedelta, timezone

import hashlib

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import models

TENANT_ID = "tenant-apex"
COMPANY_ID = "co-apex-components"
PLANT_ID = "plant-pune-01"
DEPT_PURCHASE = "dept-purchase"
DEPT_STORES = "dept-stores"
DEPT_GATE = "dept-gate"
DEPT_QUALITY = "dept-quality"
DEPT_LEADERSHIP = "dept-leadership"
ITEM_ID = "item-rm-304"
ALUMINIUM_ITEM_ID = "item-ali-102"
COPPER_ITEM_ID = "item-cu-201"
CASE_ID = "CASE-2026-0142"
REQ_ID = "REQ-2026-0007"
RFQ_ID = "RFQ-2026-0031"
PO_ID = "PO-DRAFT-2026-0019"


def dt(hours: int = 0) -> datetime:
    return datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc) + timedelta(hours=hours)


def clear_database(db: Session) -> None:
    for table in reversed(models.Base.metadata.sorted_tables):
        db.execute(delete(table))


def ensure_demo_role_coverage(db: Session) -> bool:
    """Add missing baseline demo identities without resetting an existing workspace."""
    tenant = db.get(models.Tenant, TENANT_ID)
    plant = db.get(models.Plant, PLANT_ID)
    if tenant is None or plant is None:
        return False
    email = "gate.operator@genuinegigs.local"
    if db.query(models.Account).filter_by(email=email).first():
        return False
    password = hash_password("Password@123")
    if db.get(models.Department, DEPT_GATE) is None:
        db.add(models.Department(
            id=DEPT_GATE, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Gate Operations",
        ))
    if db.get(models.RoleDefinition, "gate_operator") is None:
        db.add(models.RoleDefinition(id="gate_operator", label="Gate Operator", permissions=[]))
    account = models.Account(
        id="acct-usr-gate-001", email=email, name="Sanjay Patil",
        password_hash=password, email_verified_at=dt(),
    )
    user = models.User(
        id="usr-gate-001", account_id=account.id, tenant_id=TENANT_ID, plant_id=PLANT_ID,
        department_id=DEPT_GATE, name="Sanjay Patil", email=email, role="gate_operator",
        password_hash=password, manager_id="usr-plant-001",
    )
    membership = models.WorkspaceMembership(
        id="mem-usr-gate-001", account_id=account.id, tenant_id=TENANT_ID,
        user_id=user.id, default_plant_id=PLANT_ID, plant_ids=[PLANT_ID],
        department_id=DEPT_GATE, role="gate_operator",
        manager_membership_id="mem-usr-plant-001", permissions=[], status="active",
    )
    db.add_all([
        account, user, membership,
        models.UserPlantAccess(
            id="upa-usr-gate-001-plant-pune-01", tenant_id=TENANT_ID,
            user_id=user.id, plant_id=PLANT_ID, is_default=True,
        ),
        models.ReportingLine(
            id="rl-005", tenant_id=TENANT_ID,
            manager_user_id="usr-plant-001", report_user_id=user.id,
        ),
        models.AgentProfile(
            id="agt-usr-gate-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            user_id=user.id, membership_id=membership.id, role="gate_operator",
            display_name="Sanjay's Gate Operator Agent",
            allowed_actions=["explain_task", "lookup_purchase_order", "prepare_gate_entry_checklist", "collect_challan_details"],
            blocked_actions=["approve", "publish", "post_to_erp", "update_inventory", "change_master_data"],
            escalation_manager_id="usr-plant-001", enabled=bool(tenant.agent_enabled),
            escalation_policy={"manager_membership_id": "mem-usr-plant-001"},
        ),
    ])
    return True


def ensure_demo_supplier_capability_coverage(db: Session) -> int:
    """Assign every demo material to every demo supplier in the same plant."""
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.name.like("Fixture Supplier %")
        | models.Supplier.id.like("sup-steel-%")
    ).all()
    created = 0
    for supplier in suppliers:
        items = db.query(models.Item).filter_by(
            tenant_id=supplier.tenant_id, plant_id=supplier.plant_id,
        ).all()
        existing_item_ids = {
            row.item_id for row in db.query(models.SupplierItemCapability).filter_by(
                tenant_id=supplier.tenant_id, plant_id=supplier.plant_id,
                supplier_id=supplier.id,
            ).all()
        }
        for item in items:
            if item.id in existing_item_ids:
                continue
            digest = hashlib.sha256(
                f"{supplier.tenant_id}:{supplier.plant_id}:{supplier.id}:{item.id}".encode()
            ).hexdigest()[:24]
            db.add(models.SupplierItemCapability(
                id=f"demo-sic-{digest}", tenant_id=supplier.tenant_id,
                plant_id=supplier.plant_id, supplier_id=supplier.id,
                item_id=item.id, approved=True,
                notes="Demo supplier capability coverage",
            ))
            created += 1
    return created


def reset_workspace_database(db: Session, *, v2_reference_time: datetime | None = None) -> None:
    clear_database(db)
    default_password = hash_password("Password@123")

    db.add_all(
        [
            models.Tenant(
                id=TENANT_ID,
                name="Apex Components",
                slug="apex-demo",
                status="active",
                workspace_kind="demo",
                onboarding_status="complete",
                agent_enabled=True,
                feature_flags={"procurement_v2": True, "role_agents": True, "multi_agent_delegation": True, "knowledge": True,
                               "agentic_procurement_cycles": True, "prepared_work": True, "opa_governance": True,
                               "sandbox_execution": True, "async_specialists": True, "manager_cockpit": True,
                               "autonomy_centre": True, "temporal_procurement_workflow": False,
                               "tier2_automation": False, "tier3_automation": False,
                               "proactive_companion": True},
            ),
            models.Company(id=COMPANY_ID, tenant_id=TENANT_ID, name="Apex Components Pvt Ltd", erp_code="APEX-IN"),
            models.Plant(id=PLANT_ID, tenant_id=TENANT_ID, company_id=COMPANY_ID, name="Pune Plant", erp_location_code="PUNE-PLANT-STORE-01", timezone="Asia/Kolkata", currency="INR", locale="en-IN"),
            models.Plant(id="plant-nashik-01", tenant_id=TENANT_ID, company_id=COMPANY_ID, name="Nashik Plant", erp_location_code="NASHIK-PLANT-01", timezone="Asia/Kolkata", currency="INR", locale="en-IN"),
            models.Department(id=DEPT_LEADERSHIP, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Plant Leadership"),
            models.Department(id=DEPT_PURCHASE, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Purchase"),
            models.Department(id=DEPT_STORES, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Stores"),
            models.Department(id=DEPT_GATE, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Gate Operations"),
            models.Department(id=DEPT_QUALITY, tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Quality"),
        ]
    )

    roles = [
        ("plant_manager", "Plant Manager"),
        ("purchase_manager", "Purchase Manager"),
        ("purchase_executive", "Purchase Executive"),
        ("gate_operator", "Gate Operator"),
        ("store_manager", "Store Manager"),
        ("quality_inspector", "Quality Inspector"),
        ("admin", "Admin"),
    ]
    db.add_all([models.RoleDefinition(id=role, label=label, permissions=[]) for role, label in roles])

    users = [
        models.User(id="usr-plant-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_LEADERSHIP, name="Ananya Rao", email="plant.manager@genuinegigs.local", role="plant_manager", password_hash=default_password),
        models.User(id="usr-pm-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_PURCHASE, name="Vikram Shah", email="purchase.manager@genuinegigs.local", role="purchase_manager", password_hash=default_password, manager_id="usr-plant-001"),
        models.User(id="usr-pe-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_PURCHASE, name="Meera Iyer", email="purchase.exec@genuinegigs.local", role="purchase_executive", password_hash=default_password, manager_id="usr-pm-001"),
        models.User(id="usr-gate-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_GATE, name="Sanjay Patil", email="gate.operator@genuinegigs.local", role="gate_operator", password_hash=default_password, manager_id="usr-plant-001"),
        models.User(id="usr-store-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_STORES, name="Rohit Kulkarni", email="store.manager@genuinegigs.local", role="store_manager", password_hash=default_password, manager_id="usr-plant-001"),
        models.User(id="usr-quality-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_QUALITY, name="Farhan Ali", email="quality.inspector@genuinegigs.local", role="quality_inspector", password_hash=default_password, manager_id="usr-plant-001"),
        models.User(id="usr-admin-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, department_id=DEPT_LEADERSHIP, name="Neha Kapoor", email="admin@genuinegigs.local", role="admin", password_hash=default_password, manager_id="usr-plant-001"),
    ]
    db.add_all(users)
    accounts = [
        models.Account(
            id=f"acct-{user.id}",
            email=user.email,
            name=user.name,
            password_hash=default_password,
            email_verified_at=dt(),
        )
        for user in users
    ]
    for user in users:
        user.account_id = f"acct-{user.id}"
    db.add_all(accounts)
    manager_memberships = {
        "usr-pm-001": "mem-usr-plant-001",
        "usr-pe-001": "mem-usr-pm-001",
        "usr-store-001": "mem-usr-plant-001",
        "usr-gate-001": "mem-usr-plant-001",
        "usr-quality-001": "mem-usr-plant-001",
        "usr-admin-001": "mem-usr-plant-001",
    }
    memberships = [
        models.WorkspaceMembership(
            id=f"mem-{user.id}",
            account_id=f"acct-{user.id}",
            tenant_id=TENANT_ID,
            user_id=user.id,
            default_plant_id=PLANT_ID,
            plant_ids=[PLANT_ID],
            department_id=user.department_id,
            role=user.role,
            manager_membership_id=manager_memberships.get(user.id),
            permissions=[],
            status="active",
        )
        for user in users
    ]
    db.add_all(memberships)
    db.add_all(
        [
            models.UserPlantAccess(
                id=f"upa-{user.id}-{PLANT_ID}",
                tenant_id=TENANT_ID,
                user_id=user.id,
                plant_id=PLANT_ID,
                is_default=True,
            )
            for user in users
        ]
    )
    db.add_all(
        [
            models.ReportingLine(id="rl-001", tenant_id=TENANT_ID, manager_user_id="usr-plant-001", report_user_id="usr-pm-001"),
            models.ReportingLine(id="rl-002", tenant_id=TENANT_ID, manager_user_id="usr-pm-001", report_user_id="usr-pe-001"),
            models.ReportingLine(id="rl-003", tenant_id=TENANT_ID, manager_user_id="usr-plant-001", report_user_id="usr-store-001"),
            models.ReportingLine(id="rl-005", tenant_id=TENANT_ID, manager_user_id="usr-plant-001", report_user_id="usr-gate-001"),
            models.ReportingLine(id="rl-004", tenant_id=TENANT_ID, manager_user_id="usr-plant-001", report_user_id="usr-quality-001"),
        ]
    )
    agent_capabilities = {
        "plant_manager": ["explain_task", "summarize_risks", "request_updates", "delegate_down", "team_status"],
        "purchase_manager": ["explain_task", "summarize_risks", "explain_comparison", "prepare_approval_review", "request_updates"],
        "purchase_executive": ["explain_task", "draft_rfq", "extract_quote", "explain_comparison", "draft_negotiation", "create_follow_up_task"],
        "gate_operator": ["explain_task", "lookup_purchase_order", "prepare_gate_entry_checklist", "collect_challan_details"],
        "store_manager": ["explain_task", "prepare_inbound_checklist", "collect_discrepancy_evidence", "request_updates"],
        "quality_inspector": ["explain_task", "prepare_inspection_checklist", "review_certificate_evidence", "draft_disposition"],
        "admin": ["explain_task", "configuration_diagnostics", "policy_explanation"],
    }
    blocked_actions = [
        "approve_rfq",
        "publish_rfq",
        "approve_award",
        "approve_po_draft",
        "post_po_to_erp",
        "update_inventory",
        "close_case",
        "change_master_data",
        "change_permissions",
    ]
    agent_ids = {
        "usr-plant-001": "agt-plant-manager",
        "usr-pe-001": "agt-purchase-exec",
    }
    db.add_all(
        [
            models.AgentProfile(
                id=agent_ids.get(user.id, "agt-" + user.id),
                tenant_id=TENANT_ID,
                plant_id=PLANT_ID,
                user_id=user.id,
                membership_id=f"mem-{user.id}",
                role=user.role,
                display_name=f"{user.name.split(' ')[0]}'s {user.role.replace('_', ' ').title()} Agent",
                allowed_actions=agent_capabilities[user.role],
                blocked_actions=blocked_actions,
                escalation_manager_id=user.manager_id,
                prompt_version=f"{user.role}-playbook@1",
                policy_version="agent-policy@1",
                provider="groq",
                model_profile="openai/gpt-oss-120b",
                enabled=True,
                escalation_policy={"manager_membership_id": manager_memberships.get(user.id)},
            )
            for user in users
        ]
    )
    db.add_all(
        [
            models.TenantFeatureFlag(id="flag-role-agents", tenant_id=TENANT_ID, key="role_agents", enabled=True),
            models.TenantFeatureFlag(id="flag-multi-agent", tenant_id=TENANT_ID, key="multi_agent_delegation", enabled=True),
            models.TenantFeatureFlag(id="flag-knowledge", tenant_id=TENANT_ID, key="knowledge", enabled=True),
            models.TenantFeatureFlag(id="flag-procurement-v2", tenant_id=TENANT_ID, key="procurement_v2", enabled=True),
        ]
    )

    db.add(models.Uom(id="KG", label="Kilogram"))
    db.add_all([
        models.Item(id=ITEM_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, code="SLEEVE-A", name="Line shaft bearing sleeve", uom_id="KG", erp_item_code="SLEEVE-A"),
        models.Item(id=ALUMINIUM_ITEM_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, code="ALI-102", name="Aluminium Ingot", uom_id="KG", erp_item_code="ALI-102"),
        models.Item(id=COPPER_ITEM_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, code="CU-201", name="Copper Ingot", uom_id="KG", erp_item_code="CU-201"),
    ])
    db.add(
        models.ItemSpecification(
            id="spec-rm-304",
            tenant_id=TENANT_ID,
            plant_id=PLANT_ID,
            item_id=ITEM_ID,
            description="Line shaft bearing sleeve, EN8 grade, mill test certificate mandatory",
            required_certificates=["Mill Test Certificate", "Heat Number Traceability"],
        )
    )
    db.add(models.TaxPolicy(id="tax-gst18", tenant_id=TENANT_ID, plant_id=PLANT_ID, tax_code="GST18", recoverable=True, description="Baseline recoverable input GST"))

    suppliers = [
        ("sup-steel-01", "Apex Alloy Works", "approved", 91, 88, "sales@apexalloy.example", "AAW-1001"),
        ("sup-steel-02", "Bharat Metals", "approved", 83, 72, "rfq@bharatmetals.example", "BM-2044"),
        ("sup-steel-03", "Crown Industrial Supply", "conditional", 78, 95, "quotes@crownindustrial.example", "CIS-8841"),
    ]
    for supplier_id, name, status, quality, delivery, email, erp_vendor in suppliers:
        db.add(models.Supplier(id=supplier_id, tenant_id=TENANT_ID, plant_id=PLANT_ID, name=name, status=status, quality_score=quality, delivery_score=delivery, erp_vendor_id=erp_vendor))
        db.add(models.SupplierSite(id=f"{supplier_id}-site-01", tenant_id=TENANT_ID, plant_id=PLANT_ID, supplier_id=supplier_id, name=f"{name} Main Site", currency="INR", payment_terms="30 days"))
        db.add(models.SupplierContact(id=f"{supplier_id}-contact-01", tenant_id=TENANT_ID, plant_id=PLANT_ID, supplier_id=supplier_id, name=f"{name} Sales", email=email))
        db.add(models.SupplierItemCapability(id=f"cap-{supplier_id}", tenant_id=TENANT_ID, plant_id=PLANT_ID, supplier_id=supplier_id, item_id=ITEM_ID, approved=True))
        db.add(models.SupplierItemCapability(id=f"cap-ali-{supplier_id}", tenant_id=TENANT_ID, plant_id=PLANT_ID, supplier_id=supplier_id, item_id=ALUMINIUM_ITEM_ID, approved=True))
        db.add(models.SupplierItemCapability(id=f"cap-cu-{supplier_id}", tenant_id=TENANT_ID, plant_id=PLANT_ID, supplier_id=supplier_id, item_id=COPPER_ITEM_ID, approved=True))

    # Flush master records before transactional rows carrying hard foreign keys.
    db.flush()

    db.add(
        models.Case(
            id=CASE_ID,
            tenant_id=TENANT_ID,
            plant_id=PLANT_ID,
            title="Line shaft bearing sleeve commitment recovery",
            requirement="Line shaft bearing sleeve shortage for packaging line rebuild",
            supplier="Apex Alloy Works",
            owner_role="purchase_executive",
            owner_user_id="usr-pe-001",
            due_at=dt(8),
            value_amount=1810000,
            currency="INR",
            status="remaining_shortage_after_inspection",
            severity="critical",
            requirement_id=REQ_ID,
            rfq_id=RFQ_ID,
            po_draft_id=PO_ID,
            receipt_id="REC-001",
            inspection_id="INSP-001",
            timeline=[
                {"title": "Material shortage", "time": "09:00", "actor": "MRP Import", "body": "Packaging line rebuild needs 1,500 kg of line shaft bearing sleeve stock by 12-Jul."},
                {"title": "RFQ published", "time": "10:42", "actor": "Purchase Executive", "body": "RFQ-2026-0031 sent to three suppliers through approved outbox."},
                {"title": "Inspection exception", "time": "16:20", "actor": "Quality Inspector", "body": "1,430 kg accepted; 70 kg shortage remains after rejection and hold."},
            ],
            evidence=[
                {"label": "ERP reference", "value": "Oracle material: Line shaft bearing sleeve", "source": "erp", "meta": "Supplier capability and UOM mapped"},
                {"label": "Quote evidence", "value": "Apex_RFQ0031.xlsx", "source": "document", "meta": "Verified cells: price, GST, freight, lead time"},
            ],
        )
    )
    db.add(models.PurchaseRequirement(id=REQ_ID, business_number=REQ_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, source="material_shortage", item_id=ITEM_ID, quantity=1500, uom="KG", need_by_date="2026-07-12", status="approved", owner_user_id="usr-pe-001", related_case_id=CASE_ID))
    db.add(models.PurchaseRequirementLine(id="REQL-1", business_number="REQL-2026-0001", tenant_id=TENANT_ID, plant_id=PLANT_ID, requirement_id=REQ_ID, item_id=ITEM_ID, quantity=1500, uom="KG", need_by_date="2026-07-12", specification="Line shaft bearing sleeve, EN8 grade", inspection_required=True))
    db.add(models.RFQ(id=RFQ_ID, business_number=RFQ_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, requirement_id=REQ_ID, status="responses_open", deadline="2026-07-07", supplier_ids=["sup-steel-01", "sup-steel-02", "sup-steel-03"], published_at=dt(2)))
    db.add(models.RFQLine(id="RFQL-1", business_number="RFQL-2026-0001", tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, requirement_line_id="REQL-1", item_id=ITEM_ID, description="Line shaft bearing sleeve, EN8 grade, mill test certificate mandatory", quantity=1500, uom="KG", need_by_date="2026-07-12", required_certificates=["Mill Test Certificate", "Heat Number Traceability"]))
    db.flush()

    quote_rows = [
        ("Q-APEX-771", "sup-steel-01", "AAW/Q/771", "2026-07-15", "30 days from GRN", "local-xlsx-parser@1.0", "ai-disabled-template@1.0", "verified", 122.5, 4500, 1800, 5, "2026-07-10", 1000, "compliant", ["Mill Test Certificate", "Heat Number Traceability"], "Basic rate INR 122.50/kg", 0.98),
        ("Q-BHARAT-225", "sup-steel-02", "BM/225/26", "2026-07-09", "Advance 50%, balance before dispatch", "pdf-text-parser@1.0", "ai-disabled-template@1.0", "verified", 118.0, 6200, 2400, 9, "2026-07-14", 1500, "compliant", ["Mill Test Certificate", "Heat Number Traceability"], "Dispatch within 9 days", 0.90),
        ("Q-CROWN-918", "sup-steel-03", "CIS-918", "2026-07-11", "45 days from invoice", "ocr-image-parser@1.0", "ai-disabled-template@1.0", "needs_review", 120.25, 5000, 2000, 4, "2026-07-09", 2000, "missing_certificate", ["Heat Number Traceability"], "Heat traceability available", 0.75),
    ]
    for idx, (quote_id, supplier_id, number, validity, terms, parser, model, verification, price, freight, packaging, lead, promised, moq, technical, certs, evidence_text, confidence) in enumerate(quote_rows, start=1):
        db.add(models.SupplierQuote(id=quote_id, tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, supplier_id=supplier_id, quote_number=number, quote_date="2026-07-05", validity_date=validity, payment_terms=terms, parser_version=parser, model_version=model, verification_status=verification))
        db.flush()
        db.add(models.QuoteLine(id=f"QL-{idx}", tenant_id=TENANT_ID, plant_id=PLANT_ID, quote_id=quote_id, item_id=ITEM_ID, quantity=1500, uom="KG", unit_price=price, gst_rate=18, freight=freight, packaging=packaging, lead_time_days=lead, promised_date=promised, moq=moq, technical_compliance=technical, certificates=certs))
        db.add(models.QuoteExtractionRun(id=f"EXT-{idx}", tenant_id=TENANT_ID, plant_id=PLANT_ID, quote_id=quote_id, document_id=None, parser_version=parser, model_version=model, status=verification, evidence=[{"field": "unit_price" if idx == 1 else "promised_date" if idx == 2 else "certificates", "source": "xlsx:D14" if idx == 1 else "pdf:p1:x144-y660" if idx == 2 else "image:p1:region-7", "original_text": evidence_text, "confidence": confidence, "verification_status": verification}]))
        verification_values = {"unit_price": price, "promised_date": promised, "payment_terms": terms, "certificates": certs}
        for field_name, field_value in verification_values.items():
            db.add(models.QuoteFieldVerification(id=f"QFV-{idx}-{field_name}", tenant_id=TENANT_ID, plant_id=PLANT_ID, quote_id=quote_id, field_name=field_name, extracted_value=str(field_value), verified_value=str(field_value) if verification == "verified" else None, confidence=confidence, source=parser, status=verification, verified_by_user_id="usr-pe-001" if verification == "verified" else None, verified_at=dt(4) if verification == "verified" else None))
    db.flush()

    db.add(models.BidComparison(id="CMP-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, status="ready_for_manager_review", rows=[], recommended_supplier_id="sup-steel-01"))
    db.add(models.NegotiationRound(id="NEG-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, supplier_id="sup-steel-01", round_number=1, target="Reduce unit price below INR 121/kg without moving promised date.", drafted_message="Please revise to INR 121/kg while retaining 10-Jul delivery and mandatory certificates.", status="manager_approved", revised_unit_price=121.0))
    db.add(models.AwardDecision(id="AWARD-2026-004", tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, quote_id="Q-APEX-771", supplier_id="sup-steel-01", status="approved", approved_by_user_id="usr-pm-001", approved_at=dt(7), rationale="Best feasible supplier after delivery and certificate gates."))
    db.add(models.AwardDecision(id="AWARD-2026-005", tenant_id=TENANT_ID, plant_id=PLANT_ID, rfq_id=RFQ_ID, quote_id="Q-BHARAT-225", supplier_id="sup-steel-02", status="pending_approval", rationale="Contingency award proposed for the unresolved recovery quantity."))
    db.flush()
    db.add(models.PODraft(id=PO_ID, business_number=PO_ID, tenant_id=TENANT_ID, plant_id=PLANT_ID, award_id="AWARD-2026-004", supplier_id="sup-steel-01", supplier_site_id="sup-steel-01-site-01", currency="INR", payment_terms="30 days from GRN", status="simulated_posted", oracle_mapping={"vendor_id": "AAW-1001", "ship_to_location": "PUNE-PLANT-STORE-01", "item_code": "Line shaft bearing sleeve", "quantity": 1500, "uom": "KG", "unit_price": 121.0, "need_by_date": "2026-07-12", "tax_code": "GST18-RM"}, simulated_posting_correlation_id="ERP-SIM-PO-7199", approved_by_user_id="usr-pm-001", approved_at=dt(8)))
    db.flush()
    db.add(models.SupplierAcknowledgement(id="ACK-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, status="accepted", confirmed_quantity=1500, confirmed_delivery="2026-07-10"))
    db.add(models.ASN(id="ASN-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, status="in_transit", vehicle_number="MH12 AB 4421", expected_quantity=1500))
    db.flush()
    db.add(models.GateEntry(id="GATE-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, asn_id="ASN-001", status="vehicle_admitted", vehicle_number="MH12 AB 4421", received_at=dt(26)))
    db.flush()
    db.add(models.StoreReceipt(id="REC-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, gate_entry_id="GATE-001", status="short_received", received_quantity=1480, short_quantity=20))
    db.flush()
    db.add(models.InspectionResult(id="INSP-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, receipt_id="REC-001", status="partial_acceptance", inspected_quantity=1480, accepted_quantity=1430, rejected_quantity=30, held_quantity=20, certificate_status="verified"))
    db.flush()
    db.add(models.InventoryImpact(id="INV-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, po_draft_id=PO_ID, inspection_id="INSP-001", item_id=ITEM_ID, usable_quantity=1430, rejected_quantity=30, held_quantity=20))

    tasks = [
        ("TASK-101", "Verify Crown scanned quotation fields", "purchase_manager", "usr-pm-001", "open", "action", "supplier_quotes", "Q-CROWN-918"),
        ("TASK-102", "Review contingency award for recovery quantity", "purchase_manager", "usr-pm-001", "pending_approval", "critical", "award_decisions", "AWARD-2026-005"),
        ("TASK-103", "Recover remaining 70 kg shortage", "purchase_executive", "usr-pe-001", "open", "critical", "cases", CASE_ID),
    ]
    for task_id, title, role, owner, status, severity, entity_type, entity_id in tasks:
        db.add(models.Task(id=task_id, tenant_id=TENANT_ID, plant_id=PLANT_ID, title=title, owner_role=role, owner_user_id=owner, owner_membership_id=f"mem-{owner}", due_at=dt(8), status=status, severity=severity, linked_case_id=CASE_ID, entity_type=entity_type, entity_id=entity_id))

    db.add_all(
        [
            models.OutboxMessage(id="OUT-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, channel="email", recipient="sales@apexalloy.example", subject="RFQ for Line shaft bearing sleeve", body="Simulated RFQ package.", status="approved_pending_send", payload_hash="hash-rfq-0031", correlation_id="MSG-SIM-1001", idempotency_key="rfq-RFQ-2026-0031-sup-steel-01", approved_by_user_id="usr-pm-001", approved_at=dt(2)),
            models.OutboxMessage(id="OUT-002", tenant_id=TENANT_ID, plant_id=PLANT_ID, channel="erp", recipient="Oracle Purchasing Adapter", subject="Simulated PO posting PO-DRAFT-2026-0019", body="Oracle-ready PO payload.", status="simulated", payload_hash="hash-po-0019", correlation_id="ERP-SIM-PO-7199", idempotency_key="po-PO-DRAFT-2026-0019"),
        ]
    )
    db.add_all(
        [
            models.AuditEvent(id="AUD-001", tenant_id=TENANT_ID, plant_id=PLANT_ID, actor_user_id="usr-pe-001", actor="Meera Iyer", action="rfq.publish.approved_email", entity_type="rfq", entity_id=RFQ_ID, result="success", correlation_id="MSG-SIM-1001", payload_hash="hash-rfq-0031"),
            models.AuditEvent(id="AUD-002", tenant_id=TENANT_ID, plant_id=PLANT_ID, actor_user_id=None, actor="Purchasing Agent", action="quote.comparison.explained", entity_type="rfq", entity_id=RFQ_ID, result="success", correlation_id="AGT-9001", payload_hash="hash-comparison-0031", meta={"provider": "disabled", "model": "ai-disabled-template@1.0"}),
            models.AuditEvent(id="AUD-003", tenant_id=TENANT_ID, plant_id=PLANT_ID, actor_user_id="usr-pm-001", actor="Vikram Shah", action="po_draft.approved", entity_type="po_draft", entity_id=PO_ID, result="success", correlation_id="APR-PO-0019", payload_hash="hash-approve-po"),
        ]
    )

    # Canonical V2 prototype data. All flagship V2 screens consume these
    # persisted records; page components must not carry private mock arrays.
    # Tests use the canonical fixed instant. Development/demo bootstrap supplies
    # a live reference so a persistent Docker volume opens on an active shift.
    if v2_reference_time is None:
        shift_start = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)
    else:
        reference = v2_reference_time.astimezone(timezone.utc)
        shift_start = reference.replace(second=0, microsecond=0) - timedelta(hours=4)
    shift_end = shift_start + timedelta(hours=8)
    db.add(models.PlantArea(
        id="area-machining", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        name="Machining", code="MACHINING",
    ))
    lines = [
        ("line-l1", "Line 1", "L1", 2.1, 78),
        ("line-l2", "Line 2", "L2", 2.0, 82),
        ("line-l3", "Line 3", "L3", 1.95, 91),
        ("line-l4", "Line 4", "L4", 2.2, 76),
    ]
    for line_id, name, code, rate, contribution in lines:
        db.add(models.ProductionLine(
            id=line_id, tenant_id=TENANT_ID, plant_id=PLANT_ID,
            area_id="area-machining", name=name, code=code,
            standard_good_rate_per_minute=rate,
            contribution_per_good_unit=contribution,
        ))
    db.flush()
    db.add(models.PlantAsset(
        id="asset-cnc-04", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        area_id="area-machining", line_id="line-l3", name="CNC-04",
        code="CNC-04", asset_type="cnc", criticality="high",
    ))
    db.add(models.PlantShift(
        id="shift-b-2026-08-12", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        name="Shift B", code="B", starts_at=shift_start, ends_at=shift_end, status="active",
    ))
    db.add(models.EdgeGateway(
        id="edge-line3-01", tenant_id=TENANT_ID, plant_id=PLANT_ID, name="Line 3 Edge",
        runtime_version="0.1.0", certificate_fingerprint="seed-edge-line3-sha256",
        config_version=1, config_signature="seed-config-v1-signature", status="connected",
        transport="https_tls", outbound_only=True, buffer_depth=0,
        last_heartbeat_at=shift_start + timedelta(hours=3, minutes=59),
    ))
    db.flush()
    db.add_all([
        models.OperationalSetupProfile(
            id="setup-pune-v2", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            activation_stage="use_case", primary_use_case="production_loss",
            enabled_data_domains=["excel", "production", "machines", "quality", "maintenance"],
            production_calendar={"timezone": "Asia/Kolkata", "working_days": [1, 2, 3, 4, 5, 6]},
            kpi_targets={"plan_attainment": .95, "rejection_rate": .04, "downtime_minutes": 15},
            loss_categories=[{"code": "downtime", "label": "Downtime"}, {"code": "quality", "label": "Quality"}, {"code": "material", "label": "Material"}],
            escalation_rules=[{"severity": "critical", "after_minutes": 10, "role": "plant_manager"}],
            value_formulas=[{"type": "lost_output", "formula": "lost_units * contribution_per_unit"}],
            action_policies=[{"category": "downtime", "owner_role": "maintenance_technician"}],
            completed_stages=["plant", "data", "use_case"],
        ),
        models.OperationalDetectorRule(
            id="detector-production-gap", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            detector_key="production_behind_plan", name="Production behind plan",
            parameters={"current_gap_ratio": .05, "projected_gap_ratio": .05},
            severity_bands=[{"severity": "high", "current_gap_ratio": .10},
                            {"severity": "critical", "projected_gap_ratio": .15}],
            owner_role="plant_manager", source_domains=["production_plan", "production_actual"],
            approved_by_user_id="usr-admin-001",
        ),
        models.OperationalDetectorRule(
            id="detector-downtime", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            detector_key="downtime_exceeded_threshold", name="Unplanned downtime threshold",
            parameters={"high_criticality_minutes": 10, "default_minutes": 20},
            severity_bands=[{"severity": "high", "threshold_multiple": 2},
                            {"severity": "critical", "threshold_multiple": 3}],
            owner_role="maintenance_manager", source_domains=["machine", "maintenance"],
            approved_by_user_id="usr-admin-001",
        ),
        models.OperationalDetectorRule(
            id="detector-rejection", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            detector_key="rejection_rate_high", name="Rejection-rate threshold",
            parameters={"maximum_rejection_rate": .04},
            severity_bands=[{"severity": "high", "threshold_multiple": 1.5},
                            {"severity": "critical", "threshold_multiple": 2}],
            owner_role="quality_manager", source_domains=["quality"],
            approved_by_user_id="usr-admin-001",
        ),
        models.OperationalDetectorRule(
            id="detector-spc", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            detector_key="spc_control_limit_breached", name="SPC control-limit breach",
            parameters={"use_event_control_limits": True},
            severity_bands=[{"severity": "critical", "span_distance_ratio": .5}],
            owner_role="quality_manager", source_domains=["quality", "process_measurement"],
            approved_by_user_id="usr-admin-001",
        ),
        models.EdgeSourceMapping(
            id="edge-map-cnc04-state", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            gateway_id="edge-line3-01", asset_id="asset-cnc-04", protocol="opcua",
            source_address="ns=2;s=CNC04.State", canonical_signal="machine.state",
        ),
        models.EdgeSourceMapping(
            id="edge-map-cnc04-count", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            gateway_id="edge-line3-01", asset_id="asset-cnc-04", protocol="opcua",
            source_address="ns=2;s=CNC04.GoodCount", canonical_signal="production.good_count",
            source_unit="count", canonical_unit="count",
        ),
        models.EdgeSourceHealth(
            id="edge-health-cnc04", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            gateway_id="edge-line3-01", source_name="CNC-04 OPC UA", protocol="opcua",
            status="healthy", observed_at=shift_start + timedelta(hours=3, minutes=59),
        ),
    ])
    db.flush()
    targets = [930, 900, 930, 940]
    actuals = [505, 474, 381, 526]
    for index, (line_id, _, code, _, _) in enumerate(lines):
        work_order_id = f"wo-v2-{code.lower()}"
        db.add(models.ProductionWorkOrder(
            id=work_order_id, business_number=f"WO-48{index + 1}", tenant_id=TENANT_ID,
            plant_id=PLANT_ID, line_id=line_id, shift_id="shift-b-2026-08-12",
            external_reference=f"ERP-WO-48{index + 1}", product_code=f"AX-10{index + 7}",
            product_name=f"Precision assembly AX-10{index + 7}", target_quantity=targets[index],
            planned_start_at=shift_start, planned_end_at=shift_end, status="in_progress",
        ))
        db.flush()
        db.add_all([
            models.ProductionPlanPoint(
                id=f"plan-{code}-0600", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start, cumulative_quantity=0,
                source="seed",
            ),
            models.ProductionPlanPoint(
                id=f"plan-{code}-1000", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start + timedelta(hours=4),
                cumulative_quantity=targets[index] / 2, source="seed",
            ),
            models.ProductionPlanPoint(
                id=f"plan-{code}-1400", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_end,
                cumulative_quantity=targets[index], source="seed",
            ),
            models.ProductionActualPoint(
                id=f"actual-{code}-0900", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start + timedelta(hours=3),
                good_quantity=max(actuals[index] - 130, 0), reject_quantity=3,
                source="seed", source_event_key=f"seed:{code}:0900",
            ),
            models.ProductionActualPoint(
                id=f"actual-{code}-1000", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start + timedelta(hours=4),
                good_quantity=actuals[index], reject_quantity=5 if code == "L3" else 2,
                source="seed", source_event_key=f"seed:{code}:1000",
            ),
        ])
        # Dense shift trajectory: enough observations to make rate changes and
        # forecast confidence visually inspectable rather than a two-point demo.
        for hour in (1, 2, 3, 5, 6, 7):
            db.add(models.ProductionPlanPoint(
                id=f"plan-{code}-{6 + hour:02d}00", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start + timedelta(hours=hour),
                cumulative_quantity=round(targets[index] * hour / 8, 2), source="seed",
            ))
        for hour, factor in ((1, .20), (2, .46)):
            db.add(models.ProductionActualPoint(
                id=f"actual-{code}-{6 + hour:02d}00", tenant_id=TENANT_ID, plant_id=PLANT_ID,
                work_order_id=work_order_id, recorded_at=shift_start + timedelta(hours=hour),
                good_quantity=round(actuals[index] * factor, 2), reject_quantity=1,
                source="seed", source_event_key=f"seed:{code}:{6 + hour:02d}00",
            ))
    db.add(models.ProductionDowntimeEvent(
        id="down-cnc04-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        work_order_id="wo-v2-l3", line_id="line-l3", asset_id="asset-cnc-04",
        started_at=shift_start + timedelta(hours=3, minutes=17),
        ended_at=shift_start + timedelta(hours=4), category="breakdown",
        reason="Fault 701: bearing temperature trip", planned=False,
    ))
    db.add_all([
        models.ProductionDowntimeEvent(
            id="down-l1-planned-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l1", line_id="line-l1", asset_id=None,
            started_at=shift_start + timedelta(hours=1, minutes=40),
            ended_at=shift_start + timedelta(hours=1, minutes=55), category="planned_downtime",
            reason="Scheduled tool inspection", planned=True,
        ),
        models.ProductionDowntimeEvent(
            id="down-l4-changeover-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l4", line_id="line-l4", asset_id=None,
            started_at=shift_start + timedelta(hours=2, minutes=12),
            ended_at=shift_start + timedelta(hours=2, minutes=34), category="changeover",
            reason="Fixture and first-piece changeover", planned=True,
        ),
    ])
    db.add_all([
        models.ProductionQualityEvent(
            id="quality-l2-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l2", line_id="line-l2",
            occurred_at=shift_start + timedelta(hours=3, minutes=45),
            inspected_quantity=180, rejected_quantity=11, event_type="rejection",
            defect_code="DIMENSIONAL", material_lot_id="LOT-QL-284", source="seed",
        ),
        models.ProductionQualityEvent(
            id="quality-spc-l2-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l2", line_id="line-l2",
            occurred_at=shift_start + timedelta(hours=3, minutes=52),
            inspected_quantity=1, rejected_quantity=1, event_type="measurement",
            defect_code="BORE_DIAMETER", material_lot_id="LOT-QL-284",
            measurement_name="Bore diameter", measurement_value=18.42,
            lower_control_limit=17.95, upper_control_limit=18.25,
            severity="high", evidence={"gauge": "CMM-02", "sample": "S-884"}, source="seed",
        ),
    ])
    db.add_all([
        models.AssetFaultEvent(
            id="fault-cnc04-701-current", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            asset_id="asset-cnc-04", work_order_id="wo-v2-l3", fault_code="701",
            message="Bearing temperature trip", occurred_at=shift_start + timedelta(hours=3, minutes=17),
            source="seed", source_event_key="seed:cnc04:701:current",
        ),
        models.AssetFaultEvent(
            id="fault-cnc04-701-history-1", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            asset_id="asset-cnc-04", work_order_id=None, fault_code="701",
            message="Bearing temperature trip", occurred_at=shift_start - timedelta(days=18),
            cleared_at=shift_start - timedelta(days=18) + timedelta(minutes=37),
            source="seed", source_event_key="seed:cnc04:701:history1",
        ),
        models.AssetFaultEvent(
            id="fault-cnc04-701-history-2", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            asset_id="asset-cnc-04", work_order_id=None, fault_code="701",
            message="Bearing temperature trip", occurred_at=shift_start - timedelta(days=39),
            cleared_at=shift_start - timedelta(days=39) + timedelta(minutes=29),
            source="seed", source_event_key="seed:cnc04:701:history2",
        ),
    ])
    db.add(models.ProductionMaterialRequirement(
        id="pmr-rm218-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        work_order_id="wo-v2-l3", item_id=ITEM_ID, material_code="RM-218",
        description="Line shaft bearing sleeve", required_quantity=1400, uom="KG",
        required_at=shift_start + timedelta(hours=6), v1_requirement_line_id="REQL-1",
    ))
    db.add(models.MaterialInventoryPosition(
        id="mip-rm218-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        item_id=ITEM_ID, material_code="RM-218", on_hand_quantity=700,
        reserved_for_other_orders=80, quality_hold_quantity=20,
        observed_at=shift_start + timedelta(hours=3, minutes=55),
        source_system="seeded_erp", source_reference="INV-RM218-0812",
    ))
    db.add_all([
        models.ProductionSupplierCommitment(
            id="psc-rm218-confirmed", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l3", item_id=ITEM_ID, material_code="RM-218",
            supplier_id="sup-steel-01", committed_quantity=300,
            committed_delivery_at=shift_start + timedelta(hours=5, minutes=15),
            acknowledged=True, reliability_score=.92, status="open",
            v1_po_draft_id=PO_ID, v1_acknowledgement_id="ACK-001",
        ),
        models.ProductionSupplierCommitment(
            id="psc-rm218-unconfirmed", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            work_order_id="wo-v2-l3", item_id=ITEM_ID, material_code="RM-218",
            supplier_id="sup-steel-02", committed_quantity=200,
            committed_delivery_at=shift_start + timedelta(hours=5, minutes=40),
            acknowledged=False, reliability_score=.81, status="open",
        ),
    ])
    db.add(models.IntegrationConnection(
        id="conn-v2-excel", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        provider="excel_csv", provider_version="1.0", name="Production workbook exchange",
        mode="read_only", status="active", capabilities=["read_production_plan", "read_production_actual", "read_inventory", "read_requirements"],
        enabled_capabilities=["read_production_plan", "read_production_actual", "read_inventory", "read_requirements"],
        writes_enabled=False, config={"stale_after_seconds": 900},
        last_checked_at=shift_start + timedelta(hours=3, minutes=58),
    ))
    db.flush()
    db.add_all([
        models.IntegrationMappingProfile(
            id="map-v2-production-v1", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            connection_id="conn-v2-excel", name="Production operations", profile_version=1,
            workbook_schema_version="1.0", mappings={"work_orders": "Production Plan", "actuals": "Production Actual", "inventory": "Inventory"},
            transforms={"trim": True, "reject_formulas": True}, ownership={"work_orders": "external_owned"}, status="active",
        ),
        models.IntegrationSyncJob(
            id="sync-v2-production-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            connection_id="conn-v2-excel", job_type="material_needs", status="completed",
            started_at=shift_start + timedelta(hours=3, minutes=57),
            finished_at=shift_start + timedelta(hours=3, minutes=59),
            summary={"counts": {"work_orders": 4, "actuals": 8, "inventory": 1},
                     "cursors": {"work_orders": "seed-v1"}},
        ),
    ])
    db.flush()
    from app.operations import service as operational_v2
    operational_v2.evaluate_production_behind_plan(
        db, db.get(models.ProductionWorkOrder, "wo-v2-l3"), shift_start + timedelta(hours=4),
    )
    operational_v2.evaluate_downtime_threshold(
        db, db.get(models.ProductionDowntimeEvent, "down-cnc04-001"), shift_start + timedelta(hours=4),
    )
    operational_v2.evaluate_rejection_rate(db, db.get(models.ProductionQualityEvent, "quality-l2-001"))
    operational_v2.evaluate_spc_control_limit(db, db.get(models.ProductionQualityEvent, "quality-spc-l2-001"))
    operational_v2.recompute_material_readiness(
        db, db.get(models.ProductionMaterialRequirement, "pmr-rm218-001"),
        shift_start + timedelta(hours=4),
    )
    quality_deviation = db.query(models.OperationalDeviation).filter_by(
        detector_key="rejection_rate_high").one()
    spc_deviation = db.query(models.OperationalDeviation).filter_by(
        detector_key="spc_control_limit_breached").one()
    downtime_deviation = db.query(models.OperationalDeviation).filter_by(
        detector_key="downtime_exceeded_threshold").one()
    downtime_action = db.query(models.OperationalAction).filter_by(deviation_id=downtime_deviation.id).one()
    quality_action = db.query(models.OperationalAction).filter_by(deviation_id=spc_deviation.id).one()
    db.add_all([
        models.OperationalActionDependency(
            id="dep-cnc04-spare-release", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            action_id=downtime_action.id, dependency_type="resource_required",
            title="Stores confirms and stages bearing BR-28", owner_role="store_manager",
            status="completed", due_at=shift_start + timedelta(hours=3, minutes=38),
            evidence_required=[{"type": "inventory_issue", "material": "BR-28"}],
            resolved_at=shift_start + timedelta(hours=3, minutes=36),
        ),
        models.OperationalActionDependency(
            id="dep-cnc04-quality-release", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            action_id=downtime_action.id, dependency_type="approval_required",
            title="Quality verifies first-off part after bearing replacement", owner_role="quality_inspector",
            status="open", due_at=shift_start + timedelta(hours=4, minutes=25),
            evidence_required=[{"type": "first_off_inspection", "work_order": "WO-483"}],
        ),
        models.OperationalActionDependency(
            id="dep-l2-lot-containment", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            action_id=quality_action.id, dependency_type="finish_to_start",
            title="Production isolates all LOT-QL-284 output after 09:30", owner_role="production_supervisor",
            status="in_progress", due_at=shift_start + timedelta(hours=4, minutes=12),
            evidence_required=[{"type": "containment_count"}, {"type": "lot_location"}],
        ),
        models.QualityContainmentRecord(
            id="containment-quality-l2-001", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            quality_event_id="quality-l2-001", deviation_id=quality_deviation.id,
            containment_type="isolate_and_inspect", affected_lot="LOT-QL-284",
            status="open", evidence=[{"type": "inspection", "reference": "QL-284"}],
        ),
        models.QualityRecoveryCase(
            id="quality-ncr-ql284", business_number="NCR-2026-0001",
            tenant_id=TENANT_ID, plant_id=PLANT_ID, case_type="ncr",
            quality_event_id="quality-spc-l2-001", deviation_id=spc_deviation.id,
            title="Bore diameter outside control limit", status="investigating",
            severity="high", owner_user_id="usr-quality-001",
            problem_statement="Bore diameter sample S-884 measured above the approved upper control limit.",
            containment_summary="Isolate LOT-QL-284 and inspect all units produced after 09:30.",
            due_at=shift_start + timedelta(days=1),
            evidence=[{"type": "measurement", "quality_event_id": "quality-spc-l2-001"}],
        ),
        models.QualityRecoveryCase(
            id="quality-capa-ql284", business_number="CAPA-2026-0001",
            tenant_id=TENANT_ID, plant_id=PLANT_ID, case_type="capa",
            parent_case_id="quality-ncr-ql284", quality_event_id="quality-spc-l2-001",
            deviation_id=spc_deviation.id, title="Stabilize bore diameter machining",
            status="action_in_progress", severity="high", owner_user_id="usr-quality-001",
            problem_statement="Tool-offset drift can allow bore diameter to move outside control limits.",
            containment_summary="Continue 100% inspection until three consecutive stable samples.",
            root_cause="Tool offset was not reset after the insert change.",
            corrective_action="Add offset verification to the insert-change standard and retrain the cell.",
            effectiveness_criteria="Three consecutive lots remain inside 17.95–18.25 mm with no recurrence.",
            due_at=shift_start + timedelta(days=7),
            evidence=[{"type": "control_plan", "reference": "CP-L2-BORE-R2"}],
        ),
        models.MaintenanceWorkRecord(
            id="maint-cnc04-701", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            asset_id="asset-cnc-04", fault_event_id="fault-cnc04-701-current",
            deviation_id=downtime_deviation.id, external_cmms_reference="CMMS-SIM-8841",
            title="Inspect and replace CNC-04 bearing BR-28", status="in_progress",
            spare_code="BR-28", spare_available=True,
            started_at=shift_start + timedelta(hours=3, minutes=31),
        ),
        models.ImprovementExperiment(
            id="experiment-cnc04-bearing", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            title="Reduce recurring CNC-04 bearing trips", opportunity_key="asset:asset-cnc-04:fault:701",
            owner_user_id="usr-plant-001", status="running",
            hypothesis="Replacing BR-28 and tightening lubrication checks will reduce fault 701 recurrence by 70%.",
            baseline={"metric": "faults_per_60_days", "value": 3, "window_days": 60},
            intervention="Replace bearing BR-28 and add a weekly temperature and lubrication standard.",
            target={"metric": "faults_per_60_days", "value": 1},
            starts_at=shift_start, ends_at=shift_start + timedelta(days=60),
            evidence=[{"type": "fault", "id": "fault-cnc04-701-current"},
                      {"type": "deviation", "id": downtime_deviation.id}],
        ),
    ])
    db.flush()
    db.add(models.ImprovementBenefitMeasurement(
        id="benefit-cnc04-bearing-estimate", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        experiment_id="experiment-cnc04-bearing", measured_at=shift_start + timedelta(hours=4),
        metric="faults_per_60_days", baseline_value=3, observed_value=3,
        annualized_value=480000, confidence_state="estimated",
        calculation={"method": "repeat_fault_loss_annualized", "requires_post_period_verification": True},
    ))
    db.add_all([
        models.StandardKPIDefinition(
            id="kpi-plan-attainment-v1", tenant_id=TENANT_ID, plant_id=None,
            key="plan_attainment_forecast", name="Forecast plan attainment",
            description="Forecast good output divided by scheduled target for active work orders.",
            unit="ratio", formula="sum(forecast_good_quantity) / sum(target_quantity)",
            direction="higher_is_better",
            context_dimensions=["product_mix", "scheduled_minutes", "data_freshness"],
            version_label="1.0", status="active", approved_by_user_id="usr-plant-001",
            approved_at=shift_start - timedelta(days=7),
        ),
        models.StandardKPIDefinition(
            id="kpi-addressable-loss-v1", tenant_id=TENANT_ID, plant_id=None,
            key="addressable_loss_value", name="Addressable operational loss",
            description="Estimated financial exposure of active canonical deviations.",
            unit="currency", formula="sum(active_deviation.estimated_financial_impact)",
            direction="lower_is_better",
            context_dimensions=["currency", "contribution_basis", "confidence_state"],
            version_label="1.0", status="active", approved_by_user_id="usr-plant-001",
            approved_at=shift_start - timedelta(days=7),
        ),
        models.BestPracticeTransfer(
            id="practice-transfer-bearing-nashik", business_number="BPT-2026-0001",
            tenant_id=TENANT_ID, plant_id=None,
            title="Evaluate CNC bearing temperature standard at Nashik",
            source_plant_id=PLANT_ID, target_plant_id="plant-nashik-01",
            source_experiment_id="experiment-cnc04-bearing",
            source_deviation_pattern="downtime_exceeded_threshold", status="proposed",
            hypothesis="A weekly temperature and lubrication standard may reduce repeat bearing trips.",
            applicability_context={"asset_type": "cnc", "requires_local_validation": True,
                                   "source_outcome_state": "estimated"},
            expected_benefit={"metric": "repeat_faults_per_60_days", "direction": "decrease"},
            owner_user_id="usr-plant-001",
            evidence=[{"type": "experiment", "id": "experiment-cnc04-bearing"}],
        ),
        models.Notification(
            id="notification-v2-cnc04", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            user_id="usr-plant-001", category="critical", severity="critical",
            linked_entity_type="operational_deviation", linked_entity_id=downtime_deviation.id,
            navigation_target=f"/v2/deviations/{downtime_deviation.id}",
            dedupe_key="v2:incident:cnc04:701", title="CNC-04 incident",
            body="3 related fault 701 events grouped; current downtime is constraining Line 3.", status="unread",
        ),
        models.ShiftBriefing(
            id="briefing-shift-b-start", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            shift_id="shift-b-2026-08-12", briefing_type="start", status="published",
            title="Shift B operating briefing",
            summary="Three priorities need attention before the shift plan can recover.",
            metrics={"priority_count": 3},
            priorities=[{"title": "Recover CNC-04", "entity_id": downtime_deviation.id},
                        {"title": "Secure RM-218", "entity_id": "pmr-rm218-001"},
                        {"title": "Contain dimensional rejects", "entity_id": quality_deviation.id}],
            evidence=[{"type": "shift", "id": "shift-b-2026-08-12"}],
            generated_at=shift_start + timedelta(minutes=2),
            verified_by_user_id="usr-plant-001", published_at=shift_start + timedelta(minutes=3),
        ),
        models.KnowledgeDocument(
            id="knowledge-cnc04-bearing-r2", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            title="CNC-04 Bearing Temperature Trip Recovery", source="Maintenance Engineering",
            content="For fault 701, isolate CNC-04, verify bearing temperature, inspect lubrication and bearing BR-28, then perform a controlled no-load restart. Escalate if temperature exceeds 82 C.",
            approval_state="approved", document_version=2, document_type="maintenance_manual",
            revision="R2", effective_from=shift_start - timedelta(days=30),
            role_acl=["plant_manager", "maintenance_technician", "admin"], plant_acl=[PLANT_ID],
            asset_ids=["asset-cnc-04"], product_codes=[], process_codes=["machining"],
            approved_by_user_id="usr-plant-001", approved_at=shift_start - timedelta(days=30),
        ),
        models.KnowledgeDocument(
            id="knowledge-cnc04-bearing-r1", tenant_id=TENANT_ID, plant_id=PLANT_ID,
            title="CNC-04 Bearing Temperature Trip Recovery", source="Maintenance Engineering",
            content="Obsolete revision. Replace BR-17 and restart immediately.",
            approval_state="retired", document_version=1, document_type="maintenance_manual",
            revision="R1", effective_from=shift_start - timedelta(days=400),
            effective_to=shift_start - timedelta(days=31), retired_at=shift_start - timedelta(days=30),
            role_acl=["plant_manager", "maintenance_technician", "admin"], plant_acl=[PLANT_ID],
            asset_ids=["asset-cnc-04"], product_codes=[], process_codes=["machining"],
        ),
    ])
    db.flush()
    db.add(models.KnowledgeChunk(
        id="knowledge-chunk-cnc04-r2-0", tenant_id=TENANT_ID, plant_id=PLANT_ID,
        knowledge_document_id="knowledge-cnc04-bearing-r2", chunk_index=0,
        content="Fault 701 recovery: isolate CNC-04. Verify bearing temperature and lubrication. Inspect BR-28. Controlled no-load restart only after checks. Escalate above 82 C.",
        embedding=[], token_count=24, page_reference="p. 14", section_reference="4.2 Fault 701 recovery",
    ))
