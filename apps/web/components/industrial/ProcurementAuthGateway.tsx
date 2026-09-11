"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { login, type LoginWorkspaceOption, type User } from "@/lib/api";
import { roleLabel } from "@/lib/format";

const DEMO_PASSWORD = "Password@123";
const PROCUREMENT_ACCOUNTS = [
  ["purchase.manager@genuinegigs.local", "Purchase Manager"],
  ["purchase.exec@genuinegigs.local", "Purchase Executive"],
  ["plant.manager@genuinegigs.local", "Plant Manager"],
  ["gate.operator@genuinegigs.local", "Gate Operator"],
  ["store.manager@genuinegigs.local", "Stores Manager"],
  ["quality.inspector@genuinegigs.local", "Quality Inspector"],
  ["admin@genuinegigs.local", "Administrator"],
] as const;

function landingFor(user: User) {
  if (user.role === "gate_operator") return "/gate";
  if (user.role === "store_manager") return "/store";
  if (user.role === "quality_inspector") return "/quality";
  return "/procurement";
}

export function ProcurementAuthGateway() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("purchase.manager@genuinegigs.local");
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState("");
  const [workspaces, setWorkspaces] = useState<LoginWorkspaceOption[]>([]);
  const [membershipId, setMembershipId] = useState("");

  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await login(email, password, membershipId || undefined);
      if (result.requires_workspace_selection) {
        setWorkspaces(result.workspaces);
        setMembershipId("");
        return;
      }
      localStorage.setItem("gg_csrf", result.csrf_token);
      router.replace(landingFor(result.user));
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  function chooseAccount(accountEmail: string) {
    setEmail(accountEmail);
    setPassword(DEMO_PASSWORD);
    setWorkspaces([]);
    setMembershipId("");
    setError("");
  }

  return <main className="login-shell">
    <section className="login-card">
      <div className="brand-block login-brand"><div className="brand-icon" aria-hidden="true">G</div><div><div className="brand-name">GenuineGigs</div><div className="brand-subtitle">Procurement Operations</div></div></div>
      <div className="crumb">PROCUREMENT / SECURE ACCESS</div>
      <h1>Sign in to Procurement Operations</h1>
      <p>Continue from material requirement through supplier selection, purchase order, receipt, quality, and invoice handoff.</p>
      <form className="procurement-login-form" onSubmit={authenticate}>
        <label>Email</label>
        <input aria-label="Email" value={email} onChange={(event) => { setEmail(event.target.value); setWorkspaces([]); }} type="email" autoComplete="email" required />
        <details className="demo-account-picker"><summary>Use an Apex demonstration account</summary><div>{PROCUREMENT_ACCOUNTS.map(([value, label]) => <button type="button" className="small-action" key={value} onClick={() => chooseAccount(value)}>{label}</button>)}</div></details>
        <label>Password</label>
        <input aria-label="Password" value={password} onChange={(event) => { setPassword(event.target.value); setWorkspaces([]); }} type="password" autoComplete="current-password" required />
        {workspaces.length > 0 && <label>Procurement workspace<select aria-label="Workspace" value={membershipId} onChange={(event) => setMembershipId(event.target.value)} required><option value="">Choose a workspace</option>{workspaces.map((option) => <option value={option.membership_id} key={option.membership_id}>{option.workspace_name} · {option.plant_name} · {roleLabel(option.role)}</option>)}</select></label>}
        <button className="action-button wide" disabled={busy || (workspaces.length > 0 && !membershipId)}><LockKeyhole size={16}/>{busy ? "Signing in…" : workspaces.length ? "Enter selected workspace" : "Continue to procurement"}<ArrowRight size={16}/></button>
        {error && <div className="error-banner" role="alert">{error}</div>}
      </form>
      <p className="form-note">Looking for Plant Operations? <Link href="/login">Use the Plant Operations sign-in</Link>.</p>
    </section>
    <aside className="login-rail">
      <div className="rail-kicker">One governed procurement lifecycle</div>
      <h2>Move from requirement to usable material without losing evidence or ownership.</h2>
      <ul><li>Requirement and supplier RFQ</li><li>Quotation evidence and comparison</li><li>Approvals and purchase order</li><li>Gate, stores, quality, and invoice handoff</li></ul>
      <p><ShieldCheck size={17}/> Role, plant, approval, and audit controls remain enforced throughout.</p>
    </aside>
  </main>;
}
