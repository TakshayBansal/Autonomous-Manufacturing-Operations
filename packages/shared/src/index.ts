export type Severity = "info" | "action" | "critical" | "good";

export type Role =
  | "plant_manager"
  | "purchase_manager"
  | "purchase_executive"
  | "store_manager"
  | "quality_inspector"
  | "admin";

export type WorkflowStatus =
  | "open"
  | "draft"
  | "responses_open"
  | "pending_approval"
  | "approved"
  | "verified"
  | "needs_review"
  | "simulated_posted"
  | "short_received"
  | "partial_acceptance"
  | "resolved"
  | "blocked";

export type ProcurementCase = {
  id: string;
  requirement: string;
  supplier: string;
  ownerRole: Role;
  dueLabel: string;
  valueLabel: string;
  status: string;
  severity: Severity;
};

export type AgentActionPolicy = {
  allowedActions: string[];
  blockedActions: string[];
  requiresHumanApproval: boolean;
};

export type ERPMode = "simulated" | "read_only" | "write_enabled";

export const roleLabels: Record<Role, string> = {
  plant_manager: "Plant Manager",
  purchase_manager: "Purchase Manager",
  purchase_executive: "Purchase Executive",
  store_manager: "Store Manager",
  quality_inspector: "Quality Inspector",
  admin: "Admin"
};

export const guardedAgentBlockedActions = [
  "approve_rfq",
  "approve_award",
  "approve_po_draft",
  "post_po_to_erp",
  "update_inventory",
  "close_case",
  "change_supplier_master"
] as const;
