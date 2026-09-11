import { apiUrl } from "./api";

async function request<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch(apiUrl(path),{credentials:"include",cache:"no-store",...init});
  if(!response.ok){const body=await response.json().catch(()=>({})) as {detail?:string};throw new Error(body.detail??`Platform request failed (${response.status})`)}
  return response.json() as Promise<T>;
}

export type PlatformContext={tenant_id:string;plant_id:string;workspace_kind:string;contracts:string[];execution_modes:string[]};
export type PlatformMaterial={id:string;code:string;name:string;material_type:string;lifecycle_status:string};
export type PlatformAction={id:string;status:string;action_type:string;target_type:string;target_id:string;rationale:string;correlation_id:string;policy?:{allowed:boolean;requires_approval:boolean;reason_code:string}|null;approval?:{decision:string;comment?:string|null}|null;execution?:{status:string;mode:string;result:Record<string,unknown>}|null;outcome?:{verification_status:string;outcome_type:string}|null};
export type QualityIssue={id:string;entity_type:string;entity_id?:string|null;rule_key:string;severity:string;status:string;message:string};
export type PlatformCase={id:string;case_type:string;title:string;severity:string;status:string;context:Record<string,unknown>};
export type PlatformWork={id:string;title:string;status:string;priority:string;severity:string;owner_role:string;due_at?:string|null;source_type:string;source_id:string};
export type PlatformSource={id:string;key:string;name:string;system_type:string;status:string;health:Record<string,unknown>;last_success_at?:string|null};

export const getPlatformContext=()=>request<PlatformContext>("/api/v1/platform/context");
export const getPlatformMaterials=()=>request<PlatformMaterial[]>("/api/v1/platform/materials");
export const getPlatformActions=()=>request<PlatformAction[]>("/api/v1/platform/actions");
export const getPlatformQuality=()=>request<QualityIssue[]>("/api/v1/platform/data-quality");
export const getPlatformCases=()=>request<PlatformCase[]>("/api/v1/platform/cases");
export const getPlatformWork=()=>request<PlatformWork[]>("/api/v1/platform/work");
export const getPlatformSources=()=>request<PlatformSource[]>("/api/v1/platform/sources");
