"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Factory, LockKeyhole, ShieldCheck } from "lucide-react";
import { getMe, login, type LoginWorkspaceOption } from "@/lib/api";

const NORTHSTAR_PASSWORD=process.env.NEXT_PUBLIC_V2_SIMULATION_PASSWORD??"Northstar@2026";
const SHOW_NORTHSTAR_ACCOUNTS=process.env.NEXT_PUBLIC_SHOW_SIMULATION_ACCOUNTS==="true";
const NORTHSTAR_ACCOUNTS=[
  ["ananya.deshmukh@northstar-mobility.local","Ananya Deshmukh","Corporate Operations Director"],
  ["vikram.kulkarni@northstar-mobility.local","Vikram Kulkarni","Plant Manager"],
  ["meera.jadhav@northstar-mobility.local","Meera Jadhav","Production Manager"],
  ["rohit.shinde@northstar-mobility.local","Rohit Shinde","Production Supervisor"],
  ["kavita.pawar@northstar-mobility.local","Kavita Pawar","Production Operator"],
  ["suresh.more@northstar-mobility.local","Suresh More","Maintenance Manager"],
  ["imran.shaikh@northstar-mobility.local","Imran Shaikh","Maintenance Technician"],
  ["neha.bhosale@northstar-mobility.local","Neha Bhosale","Quality Manager"],
  ["pooja.salunkhe@northstar-mobility.local","Pooja Salunkhe","Quality Inspector"],
  ["aditya.joshi@northstar-mobility.local","Aditya Joshi","Purchase Manager"],
  ["snehal.patil@northstar-mobility.local","Snehal Patil","Purchase Executive"],
  ["nitin.gaikwad@northstar-mobility.local","Nitin Gaikwad","Stores Manager"],
  ["mahesh.chavan@northstar-mobility.local","Mahesh Chavan","Gate Operator"],
  ["rhea.nair@northstar-mobility.local","Rhea Nair","Workspace Administrator"],
] as const;

export function V2AuthGateway(){
  const router=useRouter();
  const params=useSearchParams();
  const [checking,setChecking]=useState(true);
  const [busy,setBusy]=useState(false);
  const [email,setEmail]=useState(params.get("email")??"");
  const [password,setPassword]=useState("");
  const [error,setError]=useState("");
  const [workspaces,setWorkspaces]=useState<LoginWorkspaceOption[]>([]);
  const [membershipId,setMembershipId]=useState("");
  const [quickAccount,setQuickAccount]=useState("");
  useEffect(()=>{let live=true;getMe().then(()=>{if(live)router.replace("/home")}).catch(()=>{if(live)setChecking(false)});return()=>{live=false}},[router]);
  async function authenticate(loginEmail:string,loginPassword:string){setBusy(true);setError("");try{const result=await login(loginEmail,loginPassword,membershipId||undefined);if(result.requires_workspace_selection){setEmail(loginEmail);setPassword(loginPassword);setWorkspaces(result.workspaces);setMembershipId("");return}localStorage.setItem("gg_csrf",result.csrf_token);router.replace("/home");router.refresh()}catch(caught){setError(caught instanceof Error?caught.message:"Sign in could not be completed.")}finally{setBusy(false)}}
  async function submit(event:FormEvent){event.preventDefault();await authenticate(email,password)}
  function chooseAccount(value:string){setQuickAccount(value);const account=NORTHSTAR_ACCOUNTS.find(item=>item[0]===value);if(account){setEmail(account[0]);setPassword(NORTHSTAR_PASSWORD);setWorkspaces([]);setMembershipId("");setError("")}}
  if(checking)return <main className="v2-auth-shell"><div className="v2-auth-check"><span className="v2-auth-mark"><Factory/></span><strong>GenuineGigs</strong><p>Restoring your secure plant workspace</p><i/></div></main>;
  return <main className="v2-auth-shell"><section className="v2-auth-card"><div className="v2-auth-brand"><span className="v2-auth-mark"><Factory/></span><div><strong>GenuineGigs</strong><small>Manufacturing Intelligence</small></div></div><div className="v2-auth-copy"><span>Secure enterprise access</span><h1>Enter your GenuineGigs workspace.</h1><p>Procurement, supply-chain planning and factory operations in one role-aware environment.</p></div>{SHOW_NORTHSTAR_ACCOUNTS&&<div className="v2-quick-login"><div><strong>Northstar test accounts</strong><small>Choose a role to fill its local credentials.</small></div><select aria-label="Northstar test account" value={quickAccount} onChange={event=>chooseAccount(event.target.value)}><option value="">Select employee and role</option>{NORTHSTAR_ACCOUNTS.map(([accountEmail,name,role])=><option key={accountEmail} value={accountEmail}>{role} · {name}</option>)}</select>{quickAccount&&<button type="button" disabled={busy} onClick={()=>authenticate(quickAccount,NORTHSTAR_PASSWORD)}>{busy?"Opening workspace…":"Sign in with this account"}<ArrowRight/></button>}</div>}<form onSubmit={submit}><label>Work email<input autoFocus={!SHOW_NORTHSTAR_ACCOUNTS} value={email} onChange={event=>setEmail(event.target.value)} type="email" autoComplete="email" required placeholder="name@company.com"/></label><label>Password<input value={password} onChange={event=>setPassword(event.target.value)} type="password" autoComplete="current-password" required placeholder="Enter your password"/></label>{workspaces.length>0&&<><label>Operating workspace<select value={membershipId} onChange={event=>setMembershipId(event.target.value)} required><option value="">Choose an isolated workspace</option>{workspaces.map(item=><option key={item.membership_id} value={item.membership_id}>{item.workspace_name} · {item.plant_name}{item.workspace_kind?` · ${item.workspace_kind}`:""}</option>)}</select></label><p className="v2-workspace-help">Workspaces do not share transactions. Choose “Unified Automotive Demo” to test the connected MAT-182 scenario, or create it later from Administration.</p></>}<button disabled={busy||(workspaces.length>0&&!membershipId)}>{busy?"Opening workspace…":workspaces.length?"Enter workspace":"Continue to GenuineGigs"}<ArrowRight/></button>{error&&<p className="v2-auth-error" role="alert">{error}</p>}</form><footer><ShieldCheck/><span>Session protected · Role, workspace and plant scoped access</span></footer></section><aside className="v2-auth-aside"><div><span>GENUINEGIGS / MANUFACTURING INTELLIGENCE</span><h2>One secure workspace for the decisions that keep manufacturing moving.</h2><p>Move between procurement, supply planning and factory operations without losing context, evidence or ownership.</p></div><dl><div><dt>01</dt><dd>See cross-module risk and assigned work</dd></div><div><dt>02</dt><dd>Enter the module where action is required</dd></div><div><dt>03</dt><dd>Verify the operational outcome</dd></div></dl></aside></main>
}
