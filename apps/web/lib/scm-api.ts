import { apiUrl } from "./api";

async function scmRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), { credentials: "include", cache: "no-store", ...init });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(payload.detail ?? `SCM request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function csrfHeaders(): HeadersInit {
  const token = typeof window === "undefined" ? "" : localStorage.getItem("gg_csrf") ?? "";
  return { "x-csrf-token": token, "Idempotency-Key": `scm-${crypto.randomUUID()}` };
}

export type SCMRun = { id:string;status:string;as_of_at:string;horizon_start:string;horizon_end:string;engine_version:string;policy_version:number;completed_at?:string|null;materials_processed:number;exceptions_generated:number;error_summary?:string|null };
export type SCMRecommendation = { id:string;action_type:string;quantity:number;current_date?:string|null;proposed_date?:string|null;reason:string;constraints_checked:Array<Record<string,unknown>>;status:string;decision_reason?:string|null;rank?:number|null;score?:number|null;score_dimensions:Record<string,unknown>;estimated_impact:Record<string,unknown> };
export type SCMRisk = { id:string;planning_run_id:string;material:{id:string;code:string;description:string;type:string};plant_id:string;first_breach_date?:string|null;stockout_date?:string|null;shortage_qty:number;recovery_date?:string|null;severity:string;priority_score:number;priority_factors:Record<string,unknown>;affected_finished_goods_count:number;affected_customers_count:number;recommended_action_count:number;supplier?:{id:string;name:string}|null;recommendations:SCMRecommendation[];explanation:Record<string,unknown>;horizon?:Array<{date:string;risk:string;closing:number}> };
export type SCMTower = { latest_run:SCMRun|null;kpis:{materials:number;critical:number;shortages_30_days:number;pull_in:number;excess:number};risks:SCMRisk[];sources:Array<{key:string;status:string;last_successful_import?:string|null;stale:boolean}> };
export type SCMMaterialDetail = { material:{id:string;code:string;description:string;type:string;base_uom:string};latest_run:SCMRun|null;risk:SCMRisk|null;projection:Array<{date:string;opening:number;supply:number;demand:number;closing:number;safety_stock:number;risk:string}>;events:Array<{id:string;type:string;date:string;quantity_delta:number;source_type:string;source_id:string;metadata:Record<string,unknown>}>;pegs:Array<{supply_event_id:string;demand_event_id:string;quantity:number;strategy:string}>;impact:Array<{material_id:string;code:string;description:string;bom_code:string;revision:string}> };
export type SCMImport = { id:string;filename:string;source_hash:string;status:string;mode:string;summary:Record<string,number>;discovery:Record<string,unknown>;created_at:string;approved_at?:string|null;rows?:Array<{id:string;sheet:string;row_number:number;external_key?:string|null;action:string;entity_type?:string|null;canonical_entity_id?:string|null;messages:Array<{field?:string;code:string;message:string}>;source:Record<string,unknown>}> };
export type SCMDataQuality = {counts:{rejected:number;conflicts:number};rows:Array<{batch_id:string;sheet:string;row_number:number;external_key?:string|null;messages:Array<{code:string;message:string}>}>;sources:Array<{key:string;status:string;last_successful_import?:string|null;stale:boolean;records_processed:number;error_summary?:string|null}>};

export const getSCMContext=()=>scmRequest<{enabled:boolean;admin_only:boolean;plant:{id:string;name:string;timezone:string;currency:string}|null}>("/scm/context");
export const getSCMTower=()=>scmRequest<SCMTower>("/scm/control-tower");
export const getSCMExceptions=(params="")=>scmRequest<SCMRisk[]>(`/scm/exceptions${params?`?${params}`:""}`);
export const getSCMMaterials=(search="")=>scmRequest<Array<{id:string;code:string;description:string;type:string;base_uom:string;severity?:string|null;stockout_date?:string|null}>>(`/scm/materials${search?`?search=${encodeURIComponent(search)}`:""}`);
export const getSCMMaterial=(id:string,granularity:"daily"|"weekly"|"monthly"="daily")=>scmRequest<SCMMaterialDetail>(`/scm/materials/${id}?granularity=${granularity}`);
export const getSCMImports=()=>scmRequest<SCMImport[]>("/scm/imports");
export const getSCMImport=(id:string)=>scmRequest<SCMImport>(`/scm/imports/${id}`);
export const getSCMDataQuality=()=>scmRequest<SCMDataQuality>("/scm/data-quality");
export const loadSCMMock=()=>scmRequest<{status:string;summary:Record<string,number>}>("/scm/mock-data/load",{method:"POST",headers:csrfHeaders()});
export const runSCMPlanning=()=>scmRequest<SCMRun>("/scm/planning-runs",{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:"{}"});
export const decideSCMRecommendation=(id:string,decision:"ACCEPTED"|"REJECTED"|"DEFERRED",reason:string)=>scmRequest<SCMRecommendation>(`/scm/recommendations/${id}/decision`,{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({decision,reason})});
export async function previewSCMImport(file:File,csvEntity?:string,mappings:Record<string,unknown>={}):Promise<SCMImport>{const body=new FormData();body.set("file",file);body.set("mappings_json",JSON.stringify(mappings));if(csvEntity)body.set("csv_entity",csvEntity);return scmRequest("/scm/imports/preview",{method:"POST",headers:csrfHeaders(),body})}
export const commitSCMImport=(id:string)=>scmRequest<SCMImport>(`/scm/imports/${id}/commit`,{method:"POST",headers:csrfHeaders()});
export type SCMMappingProfile={id:string;name:string;version:number;mappings:Record<string,unknown>;transforms:Record<string,unknown>;status:string};
export const getSCMMappingProfiles=()=>scmRequest<SCMMappingProfile[]>("/scm/mapping-profiles");
export const saveSCMMappingProfile=(name:string,mappings:Record<string,unknown>)=>scmRequest<{id:string;version:number}>("/scm/mapping-profiles",{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({name,mappings})});
export type SCMHorizonState="HEALTHY"|"WATCH"|"CRITICAL"|"EXCESS"|"UNKNOWN";
export type SCMHorizonSegment={start_date:string;end_date:string;state:SCMHorizonState;opening:number;demand:number;receipts:number;closing:number;minimum_closing:number;safety_stock:number;maximum_shortage:number};
export type SCMHorizonEvent={type:"PO_RECEIPT"|"CANCELLATION_DEADLINE"|"INTERVENTION"|"FORECAST_CHANGE";date:string;quantity?:number;label?:string;entity_id?:string;supplier?:string;status?:string;original_date?:string|null};
export type SCMHorizonWindow={start_date:string;end_date:string;severity:string;maximum_shortage:number};
export type SCMHorizonRow={material:{id:string;code:string;description:string;category?:string};case_id?:string|null;status:SCMHorizonState;supplier?:{id:string;name:string}|null;segments:SCMHorizonSegment[];events:SCMHorizonEvent[];risk_windows:SCMHorizonWindow[];coverage:{on_hand:number;on_order:number;safety_stock:number;end_balance:number;runway_days?:number|null;projected_runout?:string|null};recommendation?:SCMRecommendation|null;affected:Array<{entity_type:string;entity_id:string;label?:string}>;points:Array<{date:string;closing:number;status:string;shortage:number;excess:number}>;receipts:Array<{date:string;quantity:number;source_id:string}>};
export type SCMHorizon={run:SCMRun|null;days:number;horizon_start?:string;horizon_end?:string;plant?:{id:string;name:string}|null;summary?:{critical_materials:number;shortage_windows:number;pull_in_opportunities:number;cancellation_windows:number;at_risk_units:number};rows:SCMHorizonRow[]};
export type SCMReadiness={run:SCMRun|null;summary:Record<string,number>;products:Array<{id:string;product:{id:string;code:string;name:string};work_order_id?:string|null;required_date:string;status:string;total_components:number;covered_components:number;at_risk_components:number;blocking_components:number;components:Array<{material_id:string;required:number;available:number;shortage:number;status:string}>}>};
export type SCMAction={id:string;action_type:string;target_type:string;target_id:string;status:string;reason:string;payload:Record<string,unknown>;expected_impact:Record<string,unknown>;created_at:string;approval?:{decision:string}|null;execution?:{status:string;external_reference?:string}|null;outcome?:{verification_status:string}|null};
export type SCMScenario={id:string;name:string;type:string;status:string;baseline_run_id?:string|null;result_run_id?:string|null;description?:string|null;overrides:Array<{id:string;type:string;material_id:string;values:Record<string,unknown>}>};
export type SCMSupplier={id:string;code?:string|null;name:string;materials_supplied:number;open_pos:number;confirmed:number;unconfirmed:number;delayed:number;delivery_score:number};
export const getSCMHorizon=(days=210,risk="")=>scmRequest<SCMHorizon>(`/scm/supply-horizon?days=${days}${risk?`&risk=${risk}`:""}`);
export const getSCMReadiness=()=>scmRequest<SCMReadiness>("/scm/readiness");
export const getSCMActions=()=>scmRequest<SCMAction[]>("/scm/actions");
export const getSCMScenarios=()=>scmRequest<SCMScenario[]>("/scm/scenarios");
export const createSCMScenario=(name:string,description="")=>scmRequest<{id:string}>("/scm/scenarios",{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({name,description})});
export const addSCMScenarioOverride=(id:string,payload:Record<string,unknown>)=>scmRequest(`/scm/scenarios/${id}/overrides`,{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify(payload)});
export const runSCMScenario=(id:string)=>scmRequest<SCMRun>(`/scm/scenarios/${id}/run`,{method:"POST",headers:csrfHeaders()});
export const compareSCMScenario=(id:string)=>scmRequest<{baseline:Record<string,number>;scenario:Record<string,number>;delta:Record<string,number>}>(`/scm/scenarios/${id}/comparison`);
export const getSCMSuppliers=()=>scmRequest<SCMSupplier[]>("/scm/suppliers");
export const simulateSCMRecommendation=(id:string)=>scmRequest<{before:Record<string,unknown>;after:Record<string,unknown>;resolves_risk:boolean}>(`/scm/recommendations/${id}/simulate`,{method:"POST",headers:csrfHeaders()});
export const createSCMAction=(id:string)=>scmRequest<{action_intent_id:string;status:string}>(`/scm/recommendations/${id}/create-action`,{method:"POST",headers:csrfHeaders()});
export const confirmSimulatedSCMExecution=(id:string,confirmation_reference:string)=>scmRequest<{planning_run_id:string;risk_status:string;case_id?:string|null}>(`/scm/recommendations/${id}/confirm-simulated-execution`,{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({confirmation_reference})});
export const runSCMPlanningNow=()=>scmRequest<Record<string,unknown>>("/scm/planning-runs/run-now",{method:"POST",headers:csrfHeaders()});
export type SCMManualEntry={id:string;entry_type:string;material:{id:string;code:string;description:string};target_entity_type?:string|null;target_entity_id?:string|null;supplier_id?:string|null;values:Record<string,unknown>;previous_values:Record<string,unknown>;reason:string;status:string;correlation_id:string;planning_run_id?:string|null;planning_status?:string|null;effective_at:string;created_at:string};
export type SCMDataEntryOptions={entry_types:string[];materials:Array<{id:string;code:string;description:string;uom:string}>;suppliers:Array<{id:string;code?:string|null;name:string}>;schedules:Array<{id:string;order_id:string;order_number:string;material_id:string;supplier_id?:string|null;due_date:string;quantity:number;status:string}>;demands:Array<{id:string;material_id:string;reference:string;required_date:string;quantity:number;demand_type:string}>};
export type SCMDataConflict={id:string;entry_id:string;severity:string;status:string;message:string;details:Record<string,unknown>;created_at:string};
export const getSCMDataEntryOptions=()=>scmRequest<SCMDataEntryOptions>("/scm/data-entry/options");
export const getSCMDataEntries=()=>scmRequest<SCMManualEntry[]>("/scm/data-entries");
export const createSCMDataEntry=(payload:Record<string,unknown>)=>scmRequest<{entry:SCMManualEntry;planning_run:SCMRun|null;replayed:boolean}>("/scm/data-entries",{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify(payload)});
export const voidSCMDataEntry=(id:string,reason:string)=>scmRequest(`/scm/data-entries/${id}/void`,{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({reason})});
export const getSCMDataConflicts=()=>scmRequest<SCMDataConflict[]>("/scm/data-conflicts");
export const resolveSCMDataConflict=(id:string,decision:"KEEP_MANUAL"|"ACCEPT_IMPORTED",reason:string)=>scmRequest(`/scm/data-conflicts/${id}/resolve`,{method:"POST",headers:{...csrfHeaders(),"Content-Type":"application/json"},body:JSON.stringify({decision,reason})});
