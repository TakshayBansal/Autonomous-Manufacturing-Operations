package genuinegigs
default decision := {"allow": false, "requires_confirmation": false, "autonomy_tier": 0, "obligations": [], "reason_code": "default_deny", "policy_version": "agentic-procurement-v1"}
read_capability if { startswith(input.capability, "list_") }
read_capability if { startswith(input.capability, "get_") }
read_capability if { startswith(input.capability, "summarize_") }
decision := {"allow": true, "requires_confirmation": false, "autonomy_tier": 0, "obligations": ["enforce_database_scope"], "reason_code": "role_scoped_read", "policy_version": "agentic-procurement-v1"} if { read_capability; input.actor.tenant_id == input.resource.tenant_id }
decision := {"allow": true, "requires_confirmation": false, "autonomy_tier": 1, "obligations": ["private_prepared_work", "require_evidence", "enforce_database_scope"], "reason_code": "prepared_work_allowed", "policy_version": "agentic-procurement-v1"} if { startswith(input.capability, "prepare_"); input.actor.tenant_id == input.resource.tenant_id }
decision := {"allow": true, "requires_confirmation": true, "autonomy_tier": 4, "obligations": ["revalidate_entity_version", "record_human_confirmation", "enforce_database_scope"], "reason_code": "consequential_confirmation_required", "policy_version": "agentic-procurement-v1"} if { input.resource.external_effect == true; input.actor.tenant_id == input.resource.tenant_id }
