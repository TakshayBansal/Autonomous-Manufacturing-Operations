export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function browserApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
  if (typeof window === 'undefined') return configured;
  if (!configured) return '';
  const url = new URL(configured);
  const loopbackHosts = new Set(['localhost', '127.0.0.1']);
  if (loopbackHosts.has(url.hostname) && loopbackHosts.has(window.location.hostname)) {
    url.hostname = window.location.hostname;
  }
  return url.origin;
}

export function apiUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path;
  const normalized = path.startsWith("/") ? path : "/" + path;
  const base = browserApiBase();
  // Relative browser requests use one collision-free gateway. Several legacy
  // API paths (for example /procurement/requirements) are also real Next.js
  // pages, so forwarding them by their original prefix is ambiguous.
  return base ? base + normalized : `/backend${normalized}`;
}

async function responseError(response: Response) {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((row) => String((row as { msg?: string }).msg ?? row)).join(". ");
  } catch {
    // Never render an upstream HTML error document inside the product UI.
  }
  if (/^\s*<!doctype html|^\s*<html/i.test(raw)) {
    return `The application API route was not available (${response.status}). Check the web-to-API proxy and try again.`;
  }
  return raw && raw.length < 500 ? raw : `Request failed: ${response.status}`;
}

export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  tenant_id: string;
  plant_id: string;
  membership_id?: string | null;
  permissions?: string[];
  capabilities?: string[];
};

export type PlatformModuleKey = "procurement" | "scm" | "operations" | "platform";
export type PlatformAppContext = {
  user: User;
  workspace: { id: string; name: string; kind?: string | null };
  plant: { id: string; name: string; timezone: string; locale: string; currency: string } | null;
  modules: Array<{ key: PlatformModuleKey; label: string; enabled: boolean; default_route: string }>;
  notification_count: number;
  source_health: "live" | "degraded" | "unknown";
};
export type PlatformHome = {
  attention: Array<{ id: string; title: string; status: string; priority: string; owner_role?: string | null; due_at?: string | null; entity_type?: string | null; entity_id?: string | null }>;
  module_summaries: Partial<Record<"procurement" | "scm" | "operations", { state: "available" | "degraded"; primary_count: number; primary_label: string; href: string }>>;
  generated_at: string;
  operational_cases?: Array<{id:string;title:string;severity:string;priority_score:number;decision_deadline?:string|null;expected_impact_at?:string|null;recovery_state:string;responsible_team?:string|null}>;
  decision_count?:number; recovery_count?:number;
  exposure?:Array<{metric:string;delta:number|null;unit:string;currency?:string|null}>;
  verified_value?:Array<{metric:string;value:number|null;unit:string;currency?:string|null}>;
};
export type FactoryImport = { id:string; filename:string; source_hash:string; version:string; status:string; summary:{errors?:Array<{sheet:string;row:number;messages:Array<{message:string}>}>;row_count?:number;children?:Record<string,string>;canonical_reconciliation?:Record<string,unknown>}; discovery:{sheets?:string[]}; created_at:string };
export const listFactoryImports=()=>apiFetch<FactoryImport[]>("/api/v1/platform/factory-imports");
export async function previewFactoryImport(file:File){const form=new FormData();form.append("file",file);return apiFormFetch<FactoryImport>("/api/v1/platform/factory-imports/preview",form,localStorage.getItem("gg_csrf")??"")}
export const commitFactoryImport=(id:string)=>mutate<FactoryImport>(`/api/v1/platform/factory-imports/${id}/commit`,localStorage.getItem("gg_csrf")??"");
export const loadFactoryDemo=()=>mutate<{import:FactoryImport;planning_run_id:string|null;case_count:number;case_id:string|null;case_href:string}>("/api/v1/platform/factory-imports/demo",localStorage.getItem("gg_csrf")??"");
export type GigiPageContext = { module?: "home"|"cases"|"work"|"decisions"|"procurement"|"scm"|"operations"|"platform"; route?: string; entity_type?: string; entity_id?: string; filters?: Record<string,string|number|boolean|null> };
export type GigiEvidence = { ref:string; source_type:string; source_id?:string|null; label:string; observed_at?:string|null; freshness?:string|null; path?:string|null };
export type GigiResponse = { answer:string; evidence:GigiEvidence[]; risks:Array<Record<string,unknown>>; recommendations:Array<Record<string,unknown>>; available_actions:Array<Record<string,unknown>>; uncertainties:string[]; follow_ups:string[] };
export type GigiConversation = { id:string; title:string; status:string; module_context?:string|null; context:GigiPageContext; created_at:string; updated_at:string };
export type GigiMessage = { id:string; type:string; content:string; citations:GigiEvidence[]; run_id?:string|null; created_at:string };
export type GigiInsight = {id:string;case_id?:string|null;category:string;severity:string;title:string;summary:string;evidence:Array<Record<string,unknown>>;delivery_state:string;acknowledged_at?:string|null;dismissed_at?:string|null;snoozed_until?:string|null;next_evaluation_at?:string|null;escalation_state?:string|null};
export type GigiBrief = {id:string;title:string;items:Array<{kind:string;id:string;title:string;severity:string;href:string;evidence_ref:string}>;evidence:Array<Record<string,unknown>>;generated_at:string};
export type GigiCommitment = {id:string;case_id?:string|null;deliverable:string;due_at:string;status:string;dependency_state?:string|null;evidence_requirement?:string|null};
export type GigiCasePlan = {case_id:string;understood_problem:string;strategies_evaluated:Array<Record<string,unknown>>;recommended_plan?:Record<string,unknown>|null;approval_required:boolean;action_plan?:Record<string,unknown>|null;guardrails:string[]};
export async function getGigiInsights(){return apiFetch<GigiInsight[]>("/api/v1/gigi/insights")}
export async function commandGigiInsight(id:string,command:"acknowledge"|"snooze"|"dismiss"){return mutate<GigiInsight>(`/api/v1/gigi/insights/${id}/${command}`,localStorage.getItem("gg_csrf")??"")}
export async function getGigiBrief(){return apiFetch<GigiBrief>("/api/v1/gigi/brief")}
export async function getGigiCommitments(){return apiFetch<GigiCommitment[]>("/api/v1/gigi/commitments")}
export async function investigateGigiCase(caseId:string){return mutate<Record<string,unknown>>(`/api/v1/gigi/cases/${caseId}/investigate`,localStorage.getItem("gg_csrf")??"")}
export async function planGigiCase(caseId:string){return mutate<GigiCasePlan>(`/api/v1/gigi/cases/${caseId}/plan`,localStorage.getItem("gg_csrf")??"")}

export type ControlTowerSnapshot = {
  tenant_name: string;
  plant_name: string;
  erp_mode: "simulated" | "read_only" | "write_enabled";
  open_cases: number;
  pending_approvals: number;
  supplier_exceptions: number;
  ai_disabled_ready: boolean;
  cases: Array<Record<string, unknown>>;
  quote_comparison: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
  recommendation: Record<string, unknown>;
};

export type V2Context = {
  user: { id: string; name: string; role: string };
  plant: { id: string; name: string; timezone: string; currency: string; locale: string } | null;
  shifts: Array<{ id: string; name: string; code: string; starts_at: string; ends_at: string; status: string }>;
};
export type V2RoleHome = {
  kind: "plant_manager"|"production_manager"|"supervisor"|"operator"|"maintenance"|"quality"|"purchase"|"stores"|"gate"|"admin"|"corporate";
  role:string; generated_at:string; plant_id:string; simulation:boolean;
  attention:Array<Record<string,unknown>>; data_health:Array<Record<string,unknown>>;
  trajectory?:V2Pulse; losses?:Array<Record<string,unknown>>; decisions?:Array<Record<string,unknown>>;
  bottlenecks?:Array<Record<string,unknown>>; supervisor_actions?:Array<Record<string,unknown>>;
  assigned_line_ids?:string[]; recovery_tasks?:Array<Record<string,unknown>>; immediate_actions?:Array<Record<string,unknown>>;
  assets?:Array<Record<string,unknown>>; quality?:Record<string,unknown>; material_risks?:Array<Record<string,unknown>>;
  expected_arrivals?:Array<Record<string,unknown>>; pending_gate_entries?:Array<Record<string,unknown>>;
  integration_health?:Array<Record<string,unknown>>; simulator_controls?:boolean; plants?:Array<Record<string,unknown>>;
};
export type V2SimulationState={running:boolean;speed:1|10|60;scenario:string;scenario_time:string;sequence:number;available_scenarios:string[];connector:{state:string;last_event_at?:string};lines:Record<string,{state:string;good:number;reject:number}>};
export type V2Pulse = { target: number; actual: number; expected_now: number; forecast: number; forecast_confidence: string };
export type V2DeviationSummary = { id: string; title: string; category?:string; severity: string; status: string; lost_units: number; financial_impact: number | null; currency: string; owner_role?: string | null };
export type V2Decision = { id: string; decision: string; affected_object: string; expected_impact: Record<string, unknown>; need_by?: string | null; priority: string; deviation_id: string; action_id: string };
export type V2AutomationActivity = { id: string; type: string; at: string; summary: string; entity_id: string };
export type V2RecoveryStrategy={id:string;recovery_case_id:string;strategy_type:string;title:string;description?:string|null;status:string;expected_recovered_units?:number|null;expected_recovered_time_seconds?:number|null;expected_value_recovered?:number|null;direct_cost?:number|null;implementation_time_seconds?:number|null;quality_risk_score?:number|null;safety_risk_score?:number|null;operational_risk_score?:number|null;uncertainty_score?:number|null;historical_effectiveness_score?:number|null;historical_sample_size?:number|null;estimated_success_probability?:number|null;recovery_score?:number|null;score_components:Record<string,unknown>;ranking_position?:number|null;requirements:Array<Record<string,unknown>>;required_authorities:string[];input_freshness:Record<string,unknown>;evidence:Array<Record<string,unknown>>;reasoning_summary?:string|null;unavailable_reason?:string|null;version:number};
export type V2RecoveryCase={id:string;deviation_id:string;scope_type:string;scope_id?:string|null;status:string;opened_at:string;target_state:Record<string,unknown>;baseline_state:Record<string,unknown>;business_exposure_amount?:number|null;business_exposure_currency?:string|null;selected_strategy_id?:string|null;recommended_strategy_id?:string|null;decision_reason?:string|null;override_reason?:string|null;actual_outcome:Record<string,unknown>;actual_recovered_units?:number|null;verified_value_recovered?:number|null;recovery_score?:number|null;recovery_success?:boolean|null;root_cause_status:string;strategies:V2RecoveryStrategy[];actions:V2Action[];version:number};
export type V2RecoveryOpportunity={id:string;deviation_id:string;title:string;severity:string;status:string;business_exposure_amount?:number|null;currency?:string|null;strategy?:V2RecoveryStrategy|null;decision_required:boolean;recoverability:number};
export type V2CommandCenter = { pulse: V2Pulse; loss_breakdown: Array<{category:string;lost_units:number;time_impact_minutes:number;financial_impact:number|null;currency:string}>; top_deviations: V2DeviationSummary[]; decisions_required: V2Decision[]; automation_activity: V2AutomationActivity[]; data_health: Array<Record<string, unknown>>; recovery_summary:{value_at_risk:number|null;value_addressed:number|null;verified_recovered_value_today:number|null};recovery_opportunities:V2RecoveryOpportunity[];role_focus:{role:string;question:string;relevant_deviation_ids:string[];attention_count:number;show_financial_value:boolean;show_data_health_first:boolean} };
export type V2KPIBoard = { at:string;shift_id?:string|null;groups:Array<{key:string;label:string;metrics:Array<{key:string;label:string;value:number|null;unit:string;direction:string;state:string}>}> };
export type V2LineOverview = { line: { id: string; name: string; code: string }; work_order: { id: string; number?: string | null; product: string }; state: string; target: number; actual: number; forecast: number; gap: number; top_blocker?: { id: string; title: string; severity: string } | null; freshness: string };
export type V2Action = { id: string; deviation_id?: string | null; task_id?: string | null; title: string; description?: string | null; status: string; priority: string; owner_role?: string | null; owner_user_id?: string | null; due_at?: string | null; expected_outcome: Record<string, unknown>; completion_outcome: Record<string, unknown>; version: number; dependencies?: Array<{id:string;title:string;owner_role?:string|null;status:string;due_at?:string|null;resolved_at?:string|null}>; blocked_by?:Array<{title:string;owner_role?:string|null;elapsed_minutes:number}> };
export type V2CausalContext = { chain:Array<{type:string;id?:string;label:string;state:string}>; contributors:Array<{label:string;value:unknown;state:string;source:string}>; hypotheses:Array<{title:string;confidence:string;basis:string}>; confirmed_cause?:string|null; dependencies:Array<{id:string;action_id:string;title:string;type:string;status:string;owner_role?:string|null;owner_user_id?:string|null;due_at?:string|null;evidence_required:Array<Record<string,unknown>>}>; similar_incidents:Array<{id:string;title:string;status:string;detected_at:string;resolution?:string|null}> };
export type V2Deviation = V2DeviationSummary & { category: string; subtype: string; detector_key: string; line_id?: string | null; shift_id?: string | null; work_order_id?: string | null; asset_id?: string | null; detected_at: string; started_at: string; expected_state: Record<string, unknown>; actual_state: Record<string, unknown>; forecast_state: Record<string, unknown>; time_impact_minutes: number; version: number; actions?: V2Action[]; evidence?: Array<Record<string, unknown>>; causal_context?:V2CausalContext };
export type V2LineWorkspace = { line: { id: string; name: string; code: string }; work_order: { id: string; number?: string | null; product_code: string; product_name: string } | null; forecast?: V2Pulse & { forecast_quantity: number; target_quantity: number; actual_quantity: number; gap_quantity: number; gap_pct: number; confidence: string }; trajectory?: Array<{at:string;plan?:number;actual?:number;reject?:number;forecast?:number}>; state?: string;execution_state?:string;performance_state?:string;machine_health_state?:string;quality_state?:string;recovery_state?:string;material_readiness_state?:string;recovery?:{case_id:string;status:string;strategy?:string|null;expected_recovered_units?:number|null;remaining_expected_gap:number}|null; timeline?: Array<{ id: string; type: string; start: string; end?: string | null; reason?: string | null; duration_minutes?:number; impact?:string; deviation_id?: string | null }>; loss_tree?: Array<{ category: string; lost_units: number }>; deviations?: V2Deviation[]; current_action?: V2Action | null };
export type V2MyWork = { now: V2Action[]; next: V2Action[]; waiting: V2Action[]; done_today: V2Action[] };
export type V2Material = { requirement_id: string; material: string; description: string; required: number; usable_now: number; confirmed_inbound: number; unconfirmed_inbound: number; need_by: string; state: "READY" | "WATCH" | "AT_RISK" | "BLOCKED" | "UNKNOWN"; freshness: string; v1_requirement_line_id?: string | null;owner:string;next_action:string };
export type V2ReadinessWorkOrder = { work_order: { id: string; number?: string | null; product: string; start: string }; state: V2Material["state"]; materials: V2Material[]; readiness_pct: number; risky_materials: number;biggest_risk?:string|null };
export type V2MaterialBoard = { horizon_days: number; work_orders: V2ReadinessWorkOrder[] };
export type V2ProcurementCycle = { id: string; number?: string | null; status: string; current_stage: string; waiting_on: string; wait_minutes: number; next_action: string; stages: Array<{ label: string; state: string; owner: string; entered_at?: string | null; wait_minutes: number; dependency?: string | null }> };
export type V2Integration = { id: string; name: string; provider: string; provider_version: string; mode: string; status: string; writes_enabled: boolean; capabilities: string[]; enabled_capabilities: string[]; live_customer_verified: boolean; protocols: string[]; health: { state: string; last_observed_at?: string | null; age_seconds?: number | null; stale_after_seconds: number; last_sync?: { id: string; status: string; job_type: string; summary: Record<string, unknown>; error?: string | null } | null }; mappings: Array<{ id: string; name: string; version: number; status: string; mappings: Record<string, unknown>; transforms:Record<string,unknown>; ownership: Record<string, unknown>;created_at:string }> };
export type V2IntegrationCatalogItem={provider:string;display_name:string;adapter_version:string;capabilities:string[];tested_capabilities:string[];protocols:string[];live_customer_verified:boolean};
export type V2QualityCase = { id: string; number?: string | null; case_type: "ncr" | "capa"; parent_case_id?: string | null; quality_event_id?: string | null; deviation_id?: string | null; title: string; status: string; severity: string; owner_user_id?: string | null; problem_statement: string; containment_summary?: string | null; root_cause?: string | null; corrective_action?: string | null; effectiveness_criteria?: string | null; effectiveness_result?: string | null; due_at?: string | null; verified_by_user_id?: string | null; verified_at?: string | null; closed_at?: string | null; evidence: Array<Record<string, unknown>>; version: number };
export type V2QualityWorkspace = { pulse: { rejection_rate: number; target_rejection_rate: number; fpy: number; active_holds: number; scrap_rework_impact: number | null }; pareto: Array<{ defect: string; quantity: number; value: number | null }>; deviations: V2Deviation[]; containments: Array<{ id: string; quality_event_id: string; deviation_id?: string | null; type: string; affected_lot?: string | null; status: string; disposition?: string | null; evidence: Record<string, unknown> }>; spc_signals: Array<{ id: string; measurement_name?: string | null; measurement_value: number; lower_control_limit?: number | null; upper_control_limit?: number | null; material_lot_id?: string | null; occurred_at: string; state: string }>; recovery_cases: V2QualityCase[] };
export type V2MaintenanceWorkspace = { pulse: { assets_down: number; production_impact: number; repeat_faults: number; waiting_for_spare: number }; assets: Array<{ asset: { id: string; code: string; name: string; criticality: string }; state: string; production_impact: number; current_fault?: { id: string; code: string; message?: string | null; occurred_at: string; repeat_count: number } | null; work: Array<{ id: string; title: string; status: string; version: number; owner_user_id?: string | null; spare_code?: string | null; spare_available?: boolean | null; deviation_id?: string | null; resolution?: string | null; started_at?: string | null; completed_at?: string | null }> }> };
export type V2MaintenanceAsset=V2MaintenanceWorkspace["assets"][number];
export type V2ImprovementWorkspace = { opportunities: Array<{ key: string; title: string; category: string; occurrences: number; annualized_value: number | null; evidence: Array<{ type: string; id: string }> }>;recurring_recovery_failures:Array<{signature:string;title:string;incidents:number;failed_recoveries:number;estimated_monthly_loss:number|null;recurrence_rate:number;case_ids:string[];recommendation:string}>;investigations:Array<Record<string,unknown>>; experiments: Array<{ id: string; title: string; opportunity_key: string; status: string; hypothesis: string; baseline: Record<string, unknown>; intervention: string; target: Record<string, unknown>; starts_at: string; ends_at: string; result: Record<string, unknown>; statistical_confidence?: number | null; evidence: Array<Record<string, unknown>>; benefits: Array<{ id: string; metric: string; baseline_value: number; observed_value: number; annualized_value: number | null; confidence_state: string }> }> };
export type V2PredictiveRisk = { key: string; risk_type: string; severity: string; title: string; probability: number; time_horizon: string; predicted_impact: number; unit: string; confidence: string; evidence: Array<{ type: string; id: string }>; recommended_action: string };
export type V2ForecastEvaluation={model:string;baseline:string;sample_size:number;metrics:{mae:number;mape?:number|null;baseline_mae:number;improvement_over_baseline?:number|null};status:string;limitations:string[];cases:Array<Record<string,unknown>>};
export type V2OperationalNotification = { id: string; type: string; severity: string; title: string; summary: string; entity_type?: string | null; entity_id?: string | null; href?: string | null; created_at: string };
export type V2SearchResponse = { query: string; groups: Array<{ entity: string; results: Array<{ id: string; label: string; context: string; href: string }> }> };
export type V2ShiftBriefing = { id: string; shift_id: string; type: string; status: string; title: string; summary: string; metrics: Record<string, unknown>; priorities: Array<{ title: string; entity_id?: string }>; losses: Array<Record<string, unknown>>; carry_over: Array<Record<string, unknown>>; evidence: Array<Record<string, unknown>>; generated_at: string; verified_by_user_id?: string | null; published_at?: string | null };
export type V2DetectorRule={id:string;detector_key:string;name:string;enabled:boolean;parameters:Record<string,unknown>;severity_bands:Array<Record<string,unknown>>;owner_role:string;source_domains:string[];effective_from:string;approved_by_user_id?:string|null;version:number};
export type V2Setup = { plant: { id: string; name: string; timezone:string; currency:string; locale:string } | null; hierarchy: { areas: number; lines: number; area_records:Array<{id:string;name:string;code:string;version:number}>; line_records:Array<{id:string;area_id:string;name:string;code:string;standard_good_rate_per_minute:number;contribution_per_good_unit:number;version:number}> }; stage: string; primary_use_case?: string | null; enabled_data_domains: string[]; completed_stages: string[]; detectors:V2DetectorRule[]; configuration: {production_calendar?:Record<string,unknown>;kpi_targets?:Record<string,unknown>;loss_categories?:Array<Record<string,unknown>>;escalation_rules?:Array<Record<string,unknown>>;value_formulas?:Array<Record<string,unknown>>;action_policies?:Array<Record<string,unknown>>} };
export type V2Edge = { gateways: Array<{ id: string; name: string; runtime_version: string; status: string; transport: string; outbound_only: boolean; buffer_depth: number; last_heartbeat_at?: string | null; config_version: number; mappings: Array<{ id: string; asset_id: string; protocol: string; source_address: string; canonical_signal: string }>; sources: Array<{ name: string; protocol: string; status: string; observed_at: string; message?: string | null }> }> };
export type V2PracticeTransfer = { id: string; number?: string | null; title: string; source_plant: { id:string; name:string }; target_plant: { id:string; name:string }; status: string; hypothesis: string; applicability_context: Record<string,unknown>; expected_benefit: Record<string,unknown>; source_experiment_id?: string|null; accepted_at?: string|null; completed_at?: string|null; outcome: Record<string,unknown>; evidence: Array<Record<string,unknown>>; version:number };
export type V2Corporate = { plants: Array<{ plant: { id: string; name: string }; context: { active_work_orders: number; data_available: boolean }; plan_attainment_forecast?: number | null; active_deviations: number; addressable_value: number; systemic_losses: string[] }>; standard_kpis: Array<{ id:string; key:string; name:string; description:string; unit:string; formula:string; direction:string; context_dimensions:string[]; version:string; approved_at?:string|null }>; systemic_losses: Array<{ detector: string; occurrences: number; plant_count:number; addressable_value:number; cross_site_verified:boolean }>; practice_transfers: V2PracticeTransfer[]; briefing:{ title:string; summary:string; limitations:string[]; evidence:Array<Record<string,unknown>> }; comparison_note: string };
export type V2Knowledge = { query?: string | null; results: Array<{ document: { id: string; title: string; document_type: string; revision: string; document_version: number; approval_state: string; effective_from?: string | null; effective_to?: string | null; asset_ids: string[]; product_codes: string[]; process_codes: string[] }; match: { score: number; excerpt: string; page?: string | null; section?: string | null }; warning?: string | null }>; excluded_revisions: Array<{ id: string; title: string; revision: string; approval_state: string; warning: string }>; retrieval_policy: string };

export type NavItem = { key: string; href: string; label: string; group?: 'my_work' | 'process_records' };
export type RoleMetric = { label: string; value: string; tone: "critical" | "action" | "good" | "neutral"; detail?: string | null };
export type WorkflowStage = { key: string; label: string; status: "done" | "current" | "blocked" | "waiting" | "not_started"; owner_role?: string | null; summary?: string | null };
export type NextAction = { id: string; title: string; description: string; role: string; severity: "info" | "action" | "critical" | "good"; entity_type?: string | null; entity_id?: string | null; path?: string | null; body?: Record<string, unknown> | null; version?: number | null };
export type WorkflowCycle = { id: string; title: string; subtitle: string; current_stage: string; current_owner_role: string; next_step: string; severity: "info" | "action" | "critical" | "good"; due_label: string; stages: WorkflowStage[] };
export type WorkloadBar = { label: string; value: number; total: number; tone: "critical" | "action" | "good" | "neutral" };
export type WorkItem = { id: string; title: string; plain_language_goal: string; technical_term: string; why_now: string; expected_result: string; owner_role: string; due_at?: string | null; severity: 'info' | 'action' | 'critical' | 'good'; status: string; cycle_id?: string | null; stage_key: string; entity_type?: string | null; entity_id?: string | null; href: string; required_evidence: string[]; blocked_by?: string | null; allowed_human_actions: string[]; agent_capabilities: string[]; requires_confirmation: boolean };
export type WorkspaceOverview = {
  role: string;
  default_route: string;
  nav_items: NavItem[];
  capabilities: string[];
  metrics: RoleMetric[];
  cycles: WorkflowCycle[];
  next_actions: NextAction[];
  work_items: WorkItem[];
  waiting_on: NextAction[];
  team_workload: WorkloadBar[];
  team_queue: Array<Record<string, unknown>>;
  delegated_tasks: Array<Record<string, unknown>>;
  notifications: Array<Record<string, unknown>>;
  assistant_status: {
    enabled: boolean;
    mode: 'groq' | 'limited';
    model?: string | null;
    normal_workflows_available: boolean;
  };
  delegation_targets: Array<{
    membership_id: string;
    name: string;
    role: string;
    manager_membership_id?: string | null;
  }>;
};
export type WorkspaceData = Record<string, Array<Record<string, unknown>>>;
export type WorkspaceHome = {
  badge_counts: Record<string, number>;
  attention_items: Array<Record<string, unknown>>;
  assistant_prepared: Array<Record<string, unknown>>;
  my_tasks: Array<Record<string, unknown>>;
  waiting_on_others: Array<Record<string, unknown>>;
  team_followups: Array<Record<string, unknown>>;
  recent_notifications: Array<Record<string, unknown>>;
  next_action?: ActionableWorkItem | null;
  actionable_work_items?: ActionableWorkItem[];
  cycles?: ProcurementCycleSummary[];
  cycle_groups?: Record<'mine_now' | 'waiting' | 'at_risk' | 'all_active', ProcurementCycleSummary[]>;
  daily_brief?: {
    period: string;
    generated_at: string;
    summary: string;
    sources: Array<{ type: string; id: string; href: string }>;
  };
};
export type BusinessReference = { id: string; business_number: string; label: string; secondary_context?: string | null; status?: string | null; route?: string | null };
export type ActionableWorkItem = { id: string; title: string; cycle: BusinessReference; material?: BusinessReference | null; rfq?: BusinessReference | null; supplier?: BusinessReference | null; stage_index: number; stage_count: number; stage_label: string; due_state: string; blocker?: string | null; current_owner: string; required_authority: string; required_evidence: string[]; allowed_actions: string[]; primary_route: string };
export type ProcurementCycleSummary = { id: string; business_number: string; title: string; materials: BusinessReference[]; rfqs: BusinessReference[]; health: 'on_track' | 'attention' | 'at_risk' | 'blocked'; current_stage: WorkflowStage; current_stage_index: number; next_stage?: string | null; next_owner: string; blocked_dependency?: string | null; completion_percentage: number; need_by_date?: string | null; due_at?: string | null; role_visible_actions: string[]; stages: WorkflowStage[] };
export type DurableProcurementCycle = {
  id: string;
  business_number?: string | null;
  requirement_id: string;
  current_stage: string;
  presentation_stage: string;
  health: 'on_track' | 'attention' | 'at_risk' | 'blocked';
  need_by_date?: string | null;
  status: 'active' | 'completed';
  version: number;
  evaluation: { owner_role?: string | null; conditions_to_advance: string[]; missing_assignment: boolean; production_risk: string; completion_percentage: number };
  stages: Array<{ key: string; label: string; status: WorkflowStage['status']; owner_role?: string | null; evidence: Array<Record<string, unknown>> }>;
  dependencies: Array<{ id: string; type: string; description: string; owner_membership_id?: string | null }>;
  risks: Array<{ id: string; type: string; severity: string; summary: string; evidence: Array<Record<string, unknown>> }>;
  prepared_work: Array<{ id: string; type: string; title: string; confidence: number; evidence: Array<Record<string, unknown>> }>;
};
export type MyDay = {
  decisions_required: Array<Record<string, unknown>>;
  prepared_for_you: Array<Record<string, unknown>>;
  do_now: Array<Record<string, unknown>>;
  waiting_on_others: DurableProcurementCycle[];
  watching: DurableProcurementCycle[];
  at_risk: DurableProcurementCycle[];
  completed_today: Array<Record<string, unknown>>;
  cycles: DurableProcurementCycle[];
};

export type CompanionAction = { id: string; label: string; mode: "manual" | "prepare" | "execute" | "explain"; href?: string };
export type CompanionIntervention = {
  id: string; title: string; message: string; why_now: string; trigger_type: string; severity: "critical" | "warning" | "action" | "info" | "success";
  priority: number; delivery_state: string; delivery_mode: "badge" | "bubble" | "panel" | "inbox";
  aggregate_version: number; actions: CompanionAction[]; evidence: Array<Record<string, unknown>>; confidence?: number | null;
  objective_id?: string | null; task_id?: string | null; run_id?: string | null; prepared_work_id?: string | null; proposal_id?: string | null;
  current_owner?: string | null; responsible_authority?: string | null; created_at: string;
};
export type CompanionPreferences = {
  proactive_level: "risk_tiered" | "mostly_silent" | "muted"; animation_mode: "system" | "full" | "reduced";
  login_briefing_enabled: boolean; sound_enabled: boolean; background_preparation_enabled: boolean;
  default_execution_mode: "manual" | "prepare";
};
export type CompanionState = {
  state: "idle" | "new" | "thinking" | "ready" | "waiting" | "confirmation" | "success" | "attention" | "urgent" | "offline";
  unresolved_count: number; running_count: number; top_intervention?: CompanionIntervention | null;
  interventions: CompanionIntervention[]; preferences: CompanionPreferences;
};
export type AgentProfile = {
  id: string;
  display_name: string;
  role: string;
  provider: string;
  model_profile: string;
  enabled: boolean;
  allowed_actions: string[];
  blocked_actions: string[];
};
export type AgentHome = {
  enabled: boolean;
  provider_mode: "groq" | "limited";
  profile: AgentProfile;
  queue: Array<Record<string, unknown>>;
  threads: Array<Record<string, unknown>>;
  runs: Array<Record<string, unknown>>;
  proposals: Array<Record<string, unknown>>;
  delegations: Array<Record<string, unknown>>;
  receipts: Array<Record<string, unknown>>;
  recent_events: Array<Record<string, unknown>>;
};
export type AgentThread = Record<string, unknown> & { id: string; title: string; thread_type: string };
export type AgentMessage = Record<string, unknown> & {
  id: string;
  message_type: string;
  content: string;
  content_format?: string;
  content_blocks?: Array<{
    type: "text" | "source_list" | "record_summary" | "field_review" | "comparison_preview" | "task_preview" | "artifact_preview" | "action_proposal" | "approval_request" | "run_progress" | "warning" | "error" | "limited_mode" | "summary" | "section" | "bullets" | "table" | "missing_information" | "sources" | "proposed_actions" | "confirmation" | "action_receipt" | "role_handoff" | "message" | "clarification" | "record_created" | "action_required" | "prepared_artifact" | "task_update" | "team_summary" | "agent_activity";
    title?: string | null;
    text?: string | null;
    items?: string[];
    columns?: string[];
    rows?: string[][];
    record?: Record<string, unknown> | null;
    actions?: Array<{ id: string; label: string; href?: string; proposal_id?: string; requires_rationale?: boolean }>;
    attachments?: Array<Record<string, unknown>>;
    fields?: Array<Record<string, unknown>>;
  }>;
  citations: Array<{ id: string; label: string; href: string; type: string }>;
  attachments?: Array<{
    id: string;
    document_id: string;
    filename: string;
    status: "uploading" | "queued" | "extracting" | "needs_mapping" | "needs_review" | "linked" | "failed" | "retrying";
    user_explanation?: string | null;
    version: number;
    inferred_rfq_id?: string | null;
    confirmed_rfq_id?: string | null;
    inferred_supplier_id?: string | null;
    confirmed_supplier_id?: string | null;
    inference_confidence?: number | null;
    inference_evidence?: Record<string, unknown>;
    extraction_id?: string | null;
    linked_quotation_id?: string | null;
    quotation_reference?: Record<string, unknown> | null;
    authorized_next_actions?: Array<{ id: "confirm_mapping" | "retry" | "review_extraction" }>;
  }>;
};
export type AgentReply = {
  run: Record<string, unknown>;
  message: AgentMessage;
  blocks?: AgentMessage['content_blocks'];
  current_work_item?: Record<string, unknown> | null;
  allowed_actions?: string[];
  created_or_updated_records?: Array<Record<string, unknown>>;
  job_status?: Record<string, unknown> | null;
  badge_counts?: Record<string, number>;
  turn_status?: "completed" | "processing" | "needs_input" | "awaiting_confirmation" | "paused_provider" | "failed";
  attachments?: AgentMessage["attachments"];
  retryable_failure?: { code: string; message: string; retryable: boolean } | null;
};
export type ProcurementCycleDetail = {
  case?: Record<string, unknown> | null;
  stages: WorkflowStage[];
  requirements: Array<Record<string, unknown>>;
  rfqs: Array<Record<string, unknown>>;
  quotes: Array<Record<string, unknown>>;
  comparisons: Array<Record<string, unknown>>;
  awards: Array<Record<string, unknown>>;
  po_drafts: Array<Record<string, unknown>>;
  negotiations: Array<Record<string, unknown>>;
  asns: Array<Record<string, unknown>>;
  gate_entries: Array<Record<string, unknown>>;
  receipts: Array<Record<string, unknown>>;
  inspections: Array<Record<string, unknown>>;
  inventory_impact: Array<Record<string, unknown>>;
  documents: Array<Record<string, unknown>>;
  outbox: Array<Record<string, unknown>>;
  integration_outbox: Array<Record<string, unknown>>;
  audit: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
};

type WorkspaceEndpoint = readonly [key: string, path: string];

function selectedCycleEndpoint(): WorkspaceEndpoint[] {
  if (typeof window === "undefined") return [];
  const cycleId = new URLSearchParams(window.location.search).get("cycle");
  return cycleId ? [["active_cycle", `/procurement/cycles/${encodeURIComponent(cycleId)}`]] : [];
}

const screenEndpoints: Record<string, WorkspaceEndpoint[]> = {
  agent: [["agent_home", "/agent/home"], ["team_status", "/agent/team-status"], ["workspaces", "/workspaces"]],
  setup: [["setup", "/workspace/setup"], ["workspaces", "/workspaces"], ["items", "/procurement/items"], ["suppliers", "/procurement/suppliers"], ["supplier_item_capabilities", "/procurement/supplier-item-capabilities"], ["material_requests", "/procurement/material-requests"], ["compliance_requirements", "/procurement/supplier-compliance/requirements"], ["supplier_certificates", "/procurement/supplier-certificates"], ["supplier_corrective_actions", "/procurement/supplier-corrective-actions"], ["knowledge", "/knowledge"]],
  control: [["tasks", "/tasks"]],
  procurement: [["requirements", "/procurement/requirements"], ["items", "/procurement/items"], ["assignees", "/procurement/assignees"]],
  approvals: [["tasks", "/tasks"], ["comparisons", "/procurement/comparison-records"], ["po_drafts", "/procurement/po-drafts"]],
  rfq: [["rfqs", "/procurement/rfqs"], ["requirements", "/procurement/requirements"], ["suppliers", "/procurement/suppliers"], ["items", "/procurement/items"]],
  quotes: [["quotes", "/procurement/quotes"], ["exchange_rates", "/procurement/exchange-rates"], ["rfqs", "/procurement/rfqs"], ["suppliers", "/procurement/suppliers"], ["documents", "/documents"]],
  evidence: [["quotes", "/procurement/quotes"], ["exchange_rates", "/procurement/exchange-rates"], ["documents", "/documents"]],
  comparison: [["rfqs", "/procurement/rfqs"], ["quotes", "/procurement/quotes"], ["comparisons", "/procurement/comparison-records"]],
  negotiations: [["negotiations", "/procurement/negotiations"], ["rfqs", "/procurement/rfqs"], ["suppliers", "/procurement/suppliers"]],
  po: [["po_drafts", "/procurement/po-drafts"], ["po_lines", "/procurement/po-lines"], ["awards", "/procurement/awards"], ["suppliers", "/procurement/suppliers"], ["supplier_contacts", "/procurement/supplier-contacts"], ["acknowledgements", "/inbound/acknowledgements"], ["outbox", "/integrations/outbox"]],
  inbound: [["acknowledgements", "/inbound/acknowledgements"], ["asns", "/inbound/asns"], ["delivery_updates", "/inbound/delivery-updates"], ["gate_entries", "/inbound/gate-entries"], ["receipts", "/inbound/receipts"], ["inspections", "/inbound/inspections"], ["supplier_returns", "/quality/supplier-returns"], ["po_drafts", "/procurement/po-drafts"]],
  gate: [["po_drafts", "/procurement/po-drafts"], ["asns", "/inbound/asns"], ["delivery_updates", "/inbound/delivery-updates"], ["gate_entries", "/inbound/gate-entries"]],
  store: [["po_drafts", "/procurement/po-drafts"], ["acknowledgements", "/inbound/acknowledgements"], ["asns", "/inbound/asns"], ["delivery_updates", "/inbound/delivery-updates"], ["documents", "/documents"], ["receipts", "/inbound/receipts"], ["gate_entries", "/inbound/gate-entries"], ["supplier_returns", "/quality/supplier-returns"]],
  quality: [["receipts", "/inbound/receipts"], ["inspections", "/inbound/inspections"], ["supplier_returns", "/quality/supplier-returns"], ["inventory_impact", "/inbound/inventory-impact"]],
  invoices: [["invoices", "/procurement/invoices"], ["invoice_extractions", "/procurement/invoice-extractions"], ["invoice_matches", "/procurement/invoice-matches"], ["finance_handoffs", "/procurement/finance-handoffs"], ["invoice_payment_statuses", "/procurement/invoice-payment-statuses"], ["po_drafts", "/procurement/po-drafts"], ["po_lines", "/procurement/po-lines"], ["suppliers", "/procurement/suppliers"]],
  cases: [["cases", "/cases"], ["tasks", "/tasks"], ["inspections", "/inbound/inspections"], ["supplier_returns", "/quality/supplier-returns"]],
  outbox: [["outbox", "/integrations/outbox"], ["erp_outbox", "/integrations/outbox/erp"], ["email_outbox", "/integrations/outbox/email"]],
  integrations: [["connections", "/integrations/connections"], ["connector_catalog", "/integrations/connectors"], ["mapping_profiles", "/integrations/excel/mapping-profiles"], ["sync_jobs", "/integrations/sync-jobs"], ["outbox", "/integrations/outbox"], ["supplier_messages", "/integrations/supplier-messages"], ["po_drafts", "/procurement/po-drafts"], ["rfqs", "/procurement/rfqs"], ["documents", "/documents"]],
  audit: [["audit", "/audit"]],
  admin: [["users", "/org/users"], ["agents", "/org/agents"], ["roles", "/org/roles"], ["plants", "/org/plants"], ["departments", "/org/departments"], ["plant_access", "/org/plant-access"], ["suppliers", "/procurement/suppliers"], ["items", "/procurement/items"], ["material_requests", "/procurement/material-requests"], ["procurement_policies", "/procurement/policies"], ["readiness", "/workspace/readiness"], ["analytics", "/workspace/analytics"]]
};

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const request = () => fetch(apiUrl(path), { ...init, credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) } });
  let response: Response;
  try { response = await request(); }
  catch (error) {
    if ((init.method ?? "GET").toUpperCase() !== "GET") throw error;
    await new Promise(resolve => setTimeout(resolve, 180));
    response = await request();
  }
  if (!response.ok) {
    // V2 pages are client-rendered and may outlive an API/session restart. Do
    // not misrepresent an expired session as missing plant or source data.
    if (response.status === 401 && typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign("/login?reason=session_expired");
    }
    throw new Error(await responseError(response));
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error(`The application API returned an unexpected response (${response.status}). Check the web-to-API proxy.`);
  }
  return response.json() as Promise<T>;
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await fetch(apiUrl(path), { credentials: "include" });
  if (!response.ok) throw new Error(await responseError(response));
  return response.blob();
}

export async function apiFormFetch<T>(path: string, form: FormData, csrfToken: string): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "x-csrf-token": csrfToken, "Idempotency-Key": crypto.randomUUID() },
    body: form
  });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return response.json() as Promise<T>;
}

export type LoginWorkspaceOption = { membership_id: string; workspace_name: string; plant_name: string; role: string; tenant_id?:string; workspace_kind?:string; onboarding_status?:string; selected?:boolean };
export type LoginResult =
  | { user: User; csrf_token: string; requires_workspace_selection?: false }
  | { requires_workspace_selection: true; workspaces: LoginWorkspaceOption[] };

export async function login(email: string, password: string, membershipId?: string) {
  return apiFetch<LoginResult>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, membership_id: membershipId || undefined }),
  });
}

export async function getMe() { return apiFetch<{ user: User }>("/auth/me"); }
export async function listWorkspaces(){return apiFetch<LoginWorkspaceOption[]>("/workspaces")}
export async function createWorkspace(payload:{workspace_name:string;company_name:string;plant_name:string;plant_code:string;agent_enabled:boolean}){return mutate<{workspace:{id:string;name:string};membership:{id:string} }>("/workspaces",localStorage.getItem("gg_csrf")??"",payload)}
export async function selectWorkspace(membershipId:string){return mutate<{csrf_token:string;membership_id:string}>("/workspaces/select",localStorage.getItem("gg_csrf")??"",{membership_id:membershipId})}
export async function getPlatformAppContext() { return apiFetch<PlatformAppContext>("/api/v1/platform/app-context"); }
export async function getPlatformHome() { return apiFetch<PlatformHome>("/api/v1/platform/home"); }
export async function createGigiConversation(page_context:GigiPageContext){return mutate<GigiConversation>("/api/v1/gigi/conversations",localStorage.getItem("gg_csrf")??"",{page_context})}
export async function listGigiConversations(){return apiFetch<GigiConversation[]>("/api/v1/gigi/conversations")}
export async function getGigiMessages(id:string){return apiFetch<GigiMessage[]>(`/api/v1/gigi/conversations/${id}/messages`)}
export async function sendGigiMessage(id:string,content:string,page_context:GigiPageContext){
  const payload={content,page_context,idempotency_key:crypto.randomUUID()};
  try{return await mutate<{message_id:string;run_id:string;response:GigiResponse}>(`/api/v1/gigi/conversations/${id}/messages`,localStorage.getItem("gg_csrf")??"",payload)}
  catch(error){if(!(error instanceof TypeError))throw error;return mutate<{message_id:string;run_id:string;response:GigiResponse}>(`/api/v1/gigi/conversations/${id}/messages`,localStorage.getItem("gg_csrf")??"",payload)}
}
export async function getV2Context() { return apiFetch<V2Context>("/api/v2/me/context"); }
export async function getV2CommandCenter(plantId: string, shiftId?: string) {
  const params = new URLSearchParams();
  if (shiftId) params.set("shift_id", shiftId);
  return apiFetch<V2CommandCenter>(`/api/v2/plants/${plantId}/command-center?${params}`);
}
function v2AtParams(shiftId?: string) { const params = new URLSearchParams(); if (shiftId) params.set("shift_id", shiftId); return params; }
export async function getV2Operations(plantId: string, shiftId?: string) { return apiFetch<{ lines: V2LineOverview[]; at: string }>(`/api/v2/plants/${plantId}/operations/overview?${v2AtParams(shiftId)}`); }
export async function getV2KPIs(plantId:string,shiftId?:string){return apiFetch<V2KPIBoard>(`/api/v2/plants/${plantId}/kpis?${v2AtParams(shiftId)}`)}
export async function getV2RoleHome(){return apiFetch<V2RoleHome>("/api/v2/home")}
export async function getV2SimulationState(){return apiFetch<V2SimulationState>("/api/v2/simulation/state")}
export async function controlV2Simulation(action:"start"|"pause"|"reset"|"speed",speed?:1|10|60){return mutate<V2SimulationState>("/api/v2/simulation/control",localStorage.getItem("gg_csrf")??"",{action,...(speed?{speed}:{})})}
export async function injectV2Scenario(key:string){return mutate<V2SimulationState>(`/api/v2/simulation/scenarios/${key}`,localStorage.getItem("gg_csrf")??"",{})}
export async function getV2LineWorkspace(lineId: string, shiftId?: string) { return apiFetch<V2LineWorkspace>(`/api/v2/lines/${lineId}/workspace?${v2AtParams(shiftId)}`); }
export async function getV2Deviation(id: string) { return apiFetch<V2Deviation>(`/api/v2/deviations/${id}`); }
export async function getV2RecoveryForDeviation(id:string){return apiFetch<V2RecoveryCase|null>(`/api/v2/deviations/${id}/recovery`)}
export async function selectV2RecoveryStrategy(caseId:string,strategyId:string,reason?:string){return mutate<{case:V2RecoveryCase;actions_created:number}>(`/api/v2/recovery-cases/${caseId}/select-strategy`,localStorage.getItem("gg_csrf")??"",{strategy_id:strategyId,reason})}
export async function startV2Recovery(caseId:string){return mutate<V2RecoveryCase>(`/api/v2/recovery-cases/${caseId}/start`,localStorage.getItem("gg_csrf")??"",{})}
export async function verifyV2Recovery(caseId:string){return mutate<{case:V2RecoveryCase;result:string}>(`/api/v2/recovery-cases/${caseId}/verify`,localStorage.getItem("gg_csrf")??"",{})}
export async function getV2MyWork() { return apiFetch<V2MyWork>("/api/v2/my-work"); }
export async function commandV2Action(id: string, command: "accept" | "start" | "wait" | "complete", body: Record<string, unknown> = {}) { return mutate<V2Action>(`/api/v2/actions/${id}/${command}`, localStorage.getItem("gg_csrf") ?? "", body); }
export async function commandV2Deviation(id: string, command: "acknowledge" | "resolve" | "verify", body: Record<string, unknown> = {}) { return mutate<V2Deviation>(`/api/v2/deviations/${id}/${command}`, localStorage.getItem("gg_csrf") ?? "", body); }
export async function getV2MaterialReadiness(horizon = 1) { return apiFetch<V2MaterialBoard>(`/api/v2/materials/readiness?horizon=${horizon}`); }
export async function getV2Procurement() { return apiFetch<V2ProcurementCycle[]>("/api/v2/materials/procurement"); }
export async function getV2Integrations() { return apiFetch<V2Integration[]>("/api/v2/integrations"); }
export async function getV2IntegrationCatalog(){return apiFetch<V2IntegrationCatalogItem[]>("/api/v2/integration-catalog")}
export async function createV2Integration(body:{provider:string;name:string;mode:string;secret_ref?:string|null;enabled_capabilities:string[]}){return mutate<V2Integration>("/api/v2/integrations",localStorage.getItem("gg_csrf")??"",body)}
export async function getV2QualityWorkspace() { return apiFetch<V2QualityWorkspace>("/api/v2/quality/workspace"); }
export async function updateV2QualityCase(id: string, body: { version: number; status: string; containment_summary?: string | null; root_cause?: string | null; corrective_action?: string | null; effectiveness_criteria?: string | null; effectiveness_result?: string | null; evidence: Array<Record<string, unknown>> }) { return mutate<V2QualityCase>(`/api/v2/quality/cases/${id}`, localStorage.getItem("gg_csrf") ?? "", body, "PUT"); }
export async function verifyV2QualityCase(id: string, version: number, effectivenessResult: string) { return mutate<V2QualityCase>(`/api/v2/quality/cases/${id}/verify`, localStorage.getItem("gg_csrf") ?? "", { version, effectiveness_result: effectivenessResult }); }
export async function closeV2QualityCase(id: string, version: number) { return mutate<V2QualityCase>(`/api/v2/quality/cases/${id}/close`, localStorage.getItem("gg_csrf") ?? "", { version, effectiveness_result: "Quality manager approved governed closure." }); }
export async function getV2MaintenanceWorkspace() { return apiFetch<V2MaintenanceWorkspace>("/api/v2/maintenance/workspace"); }
export async function getV2MaintenanceAsset(id:string){return apiFetch<V2MaintenanceAsset>(`/api/v2/maintenance/assets/${id}`)}
export async function transitionV2MaintenanceWork(id:string,command:"start"|"wait"|"complete",version:number,note="",spareAvailable?:boolean){return mutate<V2MaintenanceAsset>(`/api/v2/maintenance/work/${id}/${command}`,localStorage.getItem("gg_csrf")??"",{version,note,spare_available:spareAvailable})}
export async function getV2ImprovementWorkspace() { return apiFetch<V2ImprovementWorkspace>("/api/v2/improvement/workspace"); }
export async function getV2PredictiveRisks() { return apiFetch<V2PredictiveRisk[]>("/api/v2/intelligence/risks"); }
export async function getV2ForecastEvaluation(){return apiFetch<V2ForecastEvaluation>("/api/v2/intelligence/forecast-evaluation")}
export async function getV2Notifications() { return apiFetch<V2OperationalNotification[]>("/api/v2/notifications"); }
export async function searchV2(query: string) { return apiFetch<V2SearchResponse>(`/api/v2/search?q=${encodeURIComponent(query)}`); }
export async function getV2ShiftBriefing(shiftId: string, type = "start") { return apiFetch<V2ShiftBriefing>(`/api/v2/shifts/${shiftId}/briefing?briefing_type=${type}`); }
export async function generateV2Handover(shiftId: string) { return mutate<V2ShiftBriefing>(`/api/v2/shifts/${shiftId}/handover/generate`, localStorage.getItem("gg_csrf") ?? ""); }
export async function updateV2Handover(shiftId: string, body: Pick<V2ShiftBriefing,"summary"|"priorities"|"losses"|"carry_over">) { return apiFetch<V2ShiftBriefing>(`/api/v2/shifts/${shiftId}/handover`, { method:"PUT", headers:{"X-CSRF-Token":localStorage.getItem("gg_csrf")??""}, body:JSON.stringify(body) }); }
export async function verifyV2Handover(shiftId: string) { return mutate<V2ShiftBriefing>(`/api/v2/shifts/${shiftId}/handover/verify`, localStorage.getItem("gg_csrf") ?? ""); }
export async function publishV2Handover(shiftId: string) { return mutate<V2ShiftBriefing>(`/api/v2/shifts/${shiftId}/handover/publish`, localStorage.getItem("gg_csrf") ?? ""); }
export async function getV2Setup() { return apiFetch<V2Setup>("/api/v2/setup"); }
export async function updateV2Setup(body:{activation_stage:string;primary_use_case?:string|null;enabled_data_domains:string[];production_calendar:Record<string,unknown>;kpi_targets:Record<string,unknown>;loss_categories:Array<Record<string,unknown>>;escalation_rules:Array<Record<string,unknown>>;value_formulas:Array<Record<string,unknown>>;action_policies:Array<Record<string,unknown>>;completed_stages:string[]}) { return mutate<V2Setup>("/api/v2/setup",localStorage.getItem("gg_csrf")??"",body,"PUT"); }
export async function saveV2SetupArea(body:{name:string;code:string},id?:string) { return mutate<{id:string;name:string;code:string;version:number}>(id?`/api/v2/setup/areas/${id}`:"/api/v2/setup/areas",localStorage.getItem("gg_csrf")??"",body,id?"PUT":"POST"); }
export async function saveV2SetupLine(body:{area_id:string;name:string;code:string;standard_good_rate_per_minute:number;contribution_per_good_unit:number},id?:string) { return mutate<{id:string}>(id?`/api/v2/setup/lines/${id}`:"/api/v2/setup/lines",localStorage.getItem("gg_csrf")??"",body,id?"PUT":"POST"); }
export async function updateV2DetectorRule(rule:V2DetectorRule,body:Pick<V2DetectorRule,"enabled"|"parameters"|"severity_bands"|"owner_role">){return mutate<V2DetectorRule>(`/api/v2/setup/detectors/${rule.detector_key}`,localStorage.getItem("gg_csrf")??"",{version:rule.version,...body},"PUT")}
export async function getV2Edge() { return apiFetch<V2Edge>("/api/v2/edge"); }
export async function getV2Corporate() { return apiFetch<V2Corporate>("/api/v2/corporate/operations"); }
export async function transitionV2PracticeTransfer(id:string,version:number,status:string,outcome:Record<string,unknown>={}) { return mutate<V2PracticeTransfer>(`/api/v2/corporate/practice-transfers/${id}/transition`,localStorage.getItem("gg_csrf")??"",{version,status,outcome}); }
export async function getV2Knowledge(query = "") { return apiFetch<V2Knowledge>(query.trim() ? `/api/v2/knowledge/search?q=${encodeURIComponent(query)}` : "/api/v2/knowledge"); }
export async function testV2Integration(id: string) { return mutate<{ connection: V2Integration }>(`/api/v2/integrations/${id}/test`, localStorage.getItem("gg_csrf") ?? ""); }
export async function syncV2Integration(id: string, jobType = "material_needs") { return mutate<{ job_id: string; status: string }>(`/api/v2/integrations/${id}/sync`, localStorage.getItem("gg_csrf") ?? "", { job_type: jobType }); }
export async function updateV2IntegrationMapping(id:string,body:{name:string;mappings:Record<string,unknown>;transforms:Record<string,unknown>;ownership:Record<string,unknown>}){return mutate<{id:string;name:string;version:number;status:string}>(`/api/v2/integrations/${id}/mappings`,localStorage.getItem("gg_csrf")??"",body,"PUT")}
export async function getWorkspaceOverview() { return apiFetch<WorkspaceOverview>("/workspace/overview"); }
export async function getWorkspaceHome() { return apiFetch<WorkspaceHome>("/workspace/home"); }
export async function getMyDay() { return apiFetch<MyDay>("/workbench/my-day"); }
export async function getControlTower() { return apiFetch<ControlTowerSnapshot>("/procurement/control-tower"); }
export async function getActiveCycle() { return apiFetch<ProcurementCycleDetail>("/procurement/active-cycle"); }

export async function getWorkspaceData(screen: string, existing: WorkspaceData = {}, force = false) {
  const endpointMap = new Map<string, string>();
  [...selectedCycleEndpoint(), ...(screenEndpoints[screen] ?? [])].forEach(([key, path]) => endpointMap.set(key, path));
  const endpointsToFetch = [...endpointMap.entries()].filter(([key]) => force || !(key in existing));
  if (!endpointsToFetch.length) return existing;
  const loaded = await Promise.all(endpointsToFetch.map(async ([key, path]) => [key, await apiFetch<Array<Record<string, unknown>> | ProcurementCycleDetail>(path)] as const));
  return loaded.reduce<WorkspaceData>((data, [key, rows]) => ({ ...data, [key]: Array.isArray(rows) ? rows : [rows as Record<string, unknown>] }), { ...existing });
}

export async function mutate<T>(path: string, csrfToken: string, body?: unknown, method = "POST", version?: number | string | null) {
  return apiFetch<T>(path, { method, headers: { "x-csrf-token": csrfToken, "Idempotency-Key": crypto.randomUUID(), ...(version !== undefined && version !== null ? { "If-Match": String(version) } : {}) }, body: body ? JSON.stringify(body) : undefined });
}

export async function patch<T>(path: string, csrfToken: string, body?: unknown, version?: number | string | null) {
  return mutate<T>(path, csrfToken, body, "PATCH", version);
}

export async function uploadQuote<T>(csrfToken: string, form: FormData) {
  return apiFormFetch<T>("/procurement/quotes/upload", form, csrfToken);
}

export type QuotationIntake = {
  id: string;
  version: number;
  mode: "parsed" | "manual_comparison";
  status: "queued" | "extracting" | "needs_review" | "needs_manual_entry" | "failed" | "accepted";
  rfq_id: string;
  supplier_id?: string | null;
  supplier_candidates: Array<{ supplier_id: string; name: string; confidence: number; reason: string }>;
  fields: Record<string, unknown> & { lines?: Array<Record<string, unknown>> };
  document?: { id: string; filename: string; status: string } | null;
  parser: { provider: string; version: string; provider_job_id?: string | null };
  quote_id?: string | null;
  error?: { code: string; detail: string } | null;
};

export async function uploadQuotationIntake(csrfToken: string, form: FormData) {
  return apiFormFetch<QuotationIntake>("/procurement/quotation-intakes", form, csrfToken);
}

export async function getQuotationIntake(intakeId: string) {
  return apiFetch<QuotationIntake>(`/procurement/quotation-intakes/${intakeId}`);
}
