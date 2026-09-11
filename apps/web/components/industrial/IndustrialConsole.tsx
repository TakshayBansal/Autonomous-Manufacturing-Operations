"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Bell,
  Bot,
  Boxes,
  ClipboardCheck,
  Factory,
  FileSearch,
  FileText,
  Gauge,
  Gavel,
  History,
  Inbox,
  Landmark,
  LockKeyhole,
  Menu,
  PackageCheck,
  RadioTower,
  ShieldCheck,
  Truck,
  Upload,
  Users
} from "lucide-react";
import {
  ControlTowerSnapshot,
  LoginWorkspaceOption,
  NextAction,
  WorkItem,
  User,
  WorkspaceData,
  WorkspaceHome,
  WorkspaceOverview,
  getControlTower,
  getMe,
  getWorkspaceData,
  getWorkspaceHome,
  getMyDay,
  getWorkspaceOverview,
  apiFetch,
  apiUrl,
  login,
  mutate,
  uploadQuote,
  uploadQuotationIntake,
  getQuotationIntake,
  QuotationIntake
} from "@/lib/api";
import type { ActionableWorkItem, ProcurementCycleSummary, MyDay, DurableProcurementCycle } from "@/lib/api";
import { asText, roleLabel } from "@/lib/format";
import { useRouteSelection } from "@/lib/useRouteSelection";
import { AdminManagementPanel, ApprovalReviewPanel, CaseResolutionPanel, ComparisonV2ActionPanel, EvidenceReviewPanel, InboundV2ActionPanel, IntegrationActionPanel, InvoiceMatchingPanel, MasterDataPanel, NegotiationWorkflowPanel, OutboxControlPanel, PoArtifactPanel, RequirementCreatePanel, RequirementListPanel, SelectableRfqPanel, SupplierReturnPanel, WorkspaceSetupPanel } from "@/components/features/WorkflowForms";

import { AgentWorkspace } from '@/components/industrial/AgentWorkspace';
import { WorkspaceCommandPalette } from '@/components/industrial/WorkspaceCommandPalette';
import { ProductShell, type ProductNavItem } from '@/components/platform/ProductShell';

type Screen =
  | "agent"
  | "setup"
  | "control"
  | "procurement"
  | "approvals"
  | "rfq"
  | "quotes"
  | "evidence"
  | "comparison"
  | "negotiations"
  | "po"
  | "inbound"
  | "gate"
  | "store"
  | "quality"
  | "invoices"
  | "cases"
  | "outbox"
  | "integrations"
  | "audit"
  | "admin";

type Props = { screen: Screen };
type AuthStatus = "checking" | "authenticated" | "unauthenticated";
type PostAction = (path: string, body?: unknown, successMessage?: string, version?: number | string | null, method?: string) => Promise<void>;
type UploadAction = (form: FormData, successMessage?: string) => Promise<unknown>;
type WorkspaceMembership = LoginWorkspaceOption & { selected: boolean; tenant_id: string; agent_enabled: boolean };

let cachedUser: User | null = null;
let cachedTower: ControlTowerSnapshot | null = null;
let cachedWorkspaceData: WorkspaceData | null = null;
let cachedOverview: WorkspaceOverview | null = null;
let cachedHome: WorkspaceHome | null = null;
let cachedMyDay: MyDay | null = null;
let cachedCsrf = "";
let signInNoticeExpiresAt = 0;

const navIconByKey: Record<string, typeof Factory> = {
  agent: Bot,
  setup: Users,
  control: Factory,
  procurement: Gauge,
  approvals: ClipboardCheck,
  rfq: FileText,
  quotes: Inbox,
  evidence: FileSearch,
  comparison: Gavel,
  negotiations: RadioTower,
  po: Landmark,
  inbound: Truck,
  gate: Truck,
  store: Boxes,
  quality: PackageCheck,
  invoices: FileText,
  cases: AlertTriangle,
  outbox: Upload,
  integrations: ShieldCheck,
  audit: History,
  admin: Users
};

const screenKeys: Record<Screen, string> = {
  agent: "agent",
  setup: "setup",
  control: "control",
  procurement: "procurement",
  approvals: "approvals",
  rfq: "rfq",
  quotes: "quotes",
  evidence: "evidence",
  comparison: "comparison",
  negotiations: "negotiations",
  po: "po",
  inbound: "inbound",
  gate: "gate",
  store: "store",
  quality: "quality",
  invoices: "invoices",
  cases: "cases",
  outbox: "outbox",
  integrations: "integrations",
  audit: "audit",
  admin: "admin"
};

const screenTitles: Record<Screen, { crumb: string; title: string; subtitle: string }> = {
  agent: { crumb: "My work / Agent", title: "My role agent", subtitle: "Assigned work, cited assistance, drafts, delegations, and decisions awaiting your review." },
  setup: { crumb: 'Workspace / Setup', title: 'Workspace setup', subtitle: 'Standard roles are automatic. Add approved materials and capable suppliers, then start purchasing.' },
  control: { crumb: "Operations / Control", title: "Control centre", subtitle: "Role queues, approvals, cases, supplier risk, and inbound status." },
  procurement: { crumb: "Procurement / Step 1", title: "Material requirements", subtitle: "Enter the approved material, quantity, and required date. This starts the procurement flow." },
  approvals: { crumb: "Governance / Approvals", title: "Approval centre", subtitle: "Human approval queue before RFQ release, award, PO, or ERP dispatch." },
  rfq: { crumb: "Procurement / Step 2", title: "Supplier requests (RFQs)", subtitle: "Review one consistent request, then send it to approved suppliers." },
  quotes: { crumb: "Procurement / Step 3", title: "Supplier quotations", subtitle: "Upload quotation PDFs, review extracted fields, and verify the supplier data." },
  evidence: { crumb: "Documents / Evidence", title: "Evidence review", subtitle: "Uploaded files and parsed field evidence for the buyer review path." },
  comparison: { crumb: "Procurement / Step 4", title: "Comparison and approvals", subtitle: "Compare verified quotations and collect Plant Manager and Purchase Executive approval." },
  negotiations: { crumb: "Decision / Negotiate", title: "Negotiations", subtitle: "Commercial rounds and revised supplier positions." },
  po: { crumb: "Procurement / Step 5", title: "Purchase orders", subtitle: "Generate and download the final PO from the approved comparison." },
  inbound: { crumb: "Inbound / Tracking", title: "Inbound tracking", subtitle: "ASN, gate entry, store receipt, and inspection ledgers." },
  gate: { crumb: "Inbound / Gate", title: "Gate entry", subtitle: "Admit supplier vehicles against issued purchase orders and hand them to Stores." },
  store: { crumb: "Inbound / Store", title: "Store receipt", subtitle: "Receipt queue and store-side inbound records." },
  quality: { crumb: "Inbound / Quality", title: "Quality inspection", subtitle: "Inspection results and inventory impact." },
  cases: { crumb: "Exceptions / Cases", title: "Case register", subtitle: "Open blockers and exception closure queue." },
  outbox: { crumb: "Integrations / External delivery", title: "External delivery", subtitle: "Approved records waiting to be sent to a connected system or supplier." },
  integrations: { crumb: "Integrations / ERP", title: "Integration centre", subtitle: "Oracle, SAP, local adapter, sync job, and reconciliation status." },
  invoices: { crumb: "Procurement / Finance handoff", title: "Invoices & matching", subtitle: "Capture supplier invoices, verify order and receipt evidence, then prepare finance review." },
  audit: { crumb: "Governance / Audit", title: "Audit ledger", subtitle: "Append-only audit of user, document, approval, workflow, and integration actions." },
  admin: { crumb: "Admin / Workspace", title: "Admin workspace", subtitle: "Users, roles, agents, and guarded workspace controls." }
};

const MATERIAL_NAME = "Line shaft bearing sleeve";

screenTitles.control = {
  crumb: 'Workspace / My work',
  title: 'My work',
  subtitle: 'Approvals, assigned tasks, delegated work, exceptions, and the next authoritative action.',
};

const roleAccounts = [
  ["plant.manager@genuinegigs.local", "Plant Manager"],
  ["purchase.exec@genuinegigs.local", "Purchase Executive"],
  ["purchase.manager@genuinegigs.local", "Purchase Manager"],
  ["gate.operator@genuinegigs.local", "Gate Operator"],
  ["store.manager@genuinegigs.local", "Store Manager"],
  ["quality.inspector@genuinegigs.local", "Quality Inspector"],
  ["admin@genuinegigs.local", "Admin"]
];

export function IndustrialConsole({ screen }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const loadedOnce = useRef(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus>(cachedUser ? "authenticated" : "checking");
  const [user, setUser] = useState<User | null>(cachedUser);
  const [csrf, setCsrf] = useState(cachedCsrf);
  const [email, setEmail] = useState("plant.manager@genuinegigs.local");
  const [password, setPassword] = useState("Password@123");
  const [workspaceOptions, setWorkspaceOptions] = useState<LoginWorkspaceOption[]>([]);
  const [workspaceMembershipId, setWorkspaceMembershipId] = useState("");
  const [workspaceData, setWorkspaceData] = useState<WorkspaceData | null>(cachedWorkspaceData);
  const [tower, setTower] = useState<ControlTowerSnapshot | null>(cachedTower);
  const [overview, setOverview] = useState<WorkspaceOverview | null>(cachedOverview);
  const [home, setHome] = useState<WorkspaceHome | null>(cachedHome);
  const [myDay, setMyDay] = useState<MyDay | null>(cachedMyDay);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSignInNotice, setShowSignInNotice] = useState(() => Date.now() < signInNoticeExpiresAt);
  const [memberships, setMemberships] = useState<WorkspaceMembership[]>([]);

  useEffect(() => {
    const invitedEmail = new URLSearchParams(window.location.search).get('email');
    if (invitedEmail) setEmail(invitedEmail);
  }, []);

  useEffect(() => {
    if (authStatus === "unauthenticated") router.replace("/login");
  }, [authStatus, router]);

  useEffect(() => {
    if (authStatus !== 'authenticated') return;
    void apiFetch<WorkspaceMembership[]>('/workspaces').then(setMemberships).catch(() => setMemberships([]));
  }, [authStatus, user?.id]);

  async function switchWorkspace(membershipId: string) {
    const selected = memberships.find((membership) => membership.membership_id === membershipId);
    if (!selected || selected.selected || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await mutate<{ csrf_token: string }>('/workspaces/select', csrf || localStorage.getItem('gg_csrf') || '', { membership_id: membershipId });
      localStorage.setItem('gg_csrf', result.csrf_token);
      cachedUser = null; cachedTower = null; cachedWorkspaceData = null; cachedOverview = null; cachedHome = null; cachedMyDay = null; cachedCsrf = result.csrf_token;
      window.location.assign('/home');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Workspace could not be switched');
      setBusy(false);
    }
  }

  async function load(options: { silent?: boolean; force?: boolean } = {}) {
    if (!options.silent && !cachedUser) setAuthStatus("checking");
    try {
      const me = await getMe();
      cachedUser = me.user;
      setUser(me.user);
      setAuthStatus("authenticated");
    } catch {
      cachedUser = null;
      cachedTower = null;
      cachedWorkspaceData = null;
      cachedOverview = null;
      cachedHome = null;
      cachedMyDay = null;
      cachedCsrf = "";
      setUser(null);
      setTower(null);
      setWorkspaceData(null);
      setOverview(null);
      setHome(null);
      setMyDay(null);
      setCsrf("");
      setNotice("");
      setAuthStatus("unauthenticated");
      return null;
    }

    try {
      const overviewPayload = await getWorkspaceOverview();
      cachedOverview = overviewPayload;
      setOverview(overviewPayload);
      const canLoadScreen = screenAllowed(overviewPayload, screen);
      const [towerPayload, workspacePayload, homePayload, myDayPayload] = await Promise.all([
        options.force || !cachedTower ? getControlTower() : Promise.resolve(cachedTower),
        canLoadScreen ? getWorkspaceData(screen, cachedWorkspaceData ?? {}, Boolean(options.force)) : Promise.resolve(cachedWorkspaceData ?? {}),
        options.force || !cachedHome ? getWorkspaceHome() : Promise.resolve(cachedHome),
        screen === 'control' ? (options.force || !cachedMyDay ? getMyDay() : Promise.resolve(cachedMyDay)) : Promise.resolve(cachedMyDay),
      ]);
      cachedTower = towerPayload;
      cachedWorkspaceData = workspacePayload;
      setTower(towerPayload);
      setWorkspaceData(workspacePayload);
      cachedHome = homePayload;
      setHome(homePayload);
      cachedMyDay = myDayPayload;
      setMyDay(myDayPayload);
      setError("");
      return overviewPayload;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace data failed to load");
      return null;
    }
  }

  useEffect(() => {
    if (loadedOnce.current) return;
    loadedOnce.current = true;
    if (cachedUser && cachedTower && cachedOverview) {
      setAuthStatus("authenticated");
      if (Date.now() < signInNoticeExpiresAt) {
        window.setTimeout(() => setShowSignInNotice(false), Math.max(0, signInNoticeExpiresAt - Date.now()));
      }
      void load({ silent: true });
      return;
    }
    void load({ silent: Boolean(cachedUser) });
  }, []);

  useEffect(() => {
    const reloadSelectedCycle = () => { void load({ silent: true, force: true }); };
    window.addEventListener("genuinegigs:selection", reloadSelectedCycle);
    window.addEventListener("genuinegigs:refresh", reloadSelectedCycle);
    return () => {
      window.removeEventListener("genuinegigs:selection", reloadSelectedCycle);
      window.removeEventListener("genuinegigs:refresh", reloadSelectedCycle);
    };
  }, []);

  async function submitLogin() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = await login(email, password, workspaceMembershipId || undefined);
      if (payload.requires_workspace_selection) {
        setWorkspaceOptions(payload.workspaces);
        setWorkspaceMembershipId("");
        setNotice("Choose the workspace you want to enter.");
        return;
      }
      cachedUser = payload.user;
      cachedCsrf = payload.csrf_token;
      setUser(payload.user);
      setCsrf(payload.csrf_token);
      setAuthStatus("authenticated");
      signInNoticeExpiresAt = Date.now() + 3500;
      setShowSignInNotice(true);
      window.setTimeout(() => {
        if (Date.now() >= signInNoticeExpiresAt) setShowSignInNotice(false);
      }, 3500);
      localStorage.setItem("gg_csrf", payload.csrf_token);
      setWorkspaceOptions([]);
      setWorkspaceMembershipId("");
      const overviewPayload = await load({ silent: true, force: true });
      if (pathname === "/" || pathname === "/login") router.push("/home");
    } catch (err) {
      setNotice("");
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    const token = csrf || localStorage.getItem("gg_csrf") || "";
    setBusy(true);
    setError("");
    try {
      if (token) await mutate("/auth/logout", token);
    } catch {
      // Keep client-side sign out resilient if the server session is already gone.
    } finally {
      cachedUser = null;
      cachedTower = null;
      cachedWorkspaceData = null;
      cachedOverview = null;
      cachedCsrf = "";
      localStorage.removeItem("gg_csrf");
      setUser(null);
      setTower(null);
      setWorkspaceData(null);
      setOverview(null);
      setCsrf("");
      signInNoticeExpiresAt = 0;
      setShowSignInNotice(false);
      setNotice("");
      setAuthStatus("unauthenticated");
      setBusy(false);
      router.push("/procurement/login");
    }
  }

  async function postAction(path: string, body?: unknown, successMessage = "Workflow updated. Record timeline refreshed.", version?: number | string | null, method = "POST") {
    const token = csrf || localStorage.getItem("gg_csrf") || "";
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await mutate(path, token, body, method, version);
      await load({ silent: true, force: true });
      setNotice(successMessage);
    } catch (err) {
      setNotice("");
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadQuoteAction(form: FormData, successMessage = "Quote uploaded. Verification evidence is ready for buyer review.") {
    const token = csrf || localStorage.getItem("gg_csrf") || "";
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const parsedMode = form.get("intake_mode") === "parsed";
      form.delete("intake_mode");
      const result = parsedMode ? await uploadQuotationIntake(token, form) : await uploadQuote(token, form);
      await load({ silent: true, force: true });
      setNotice(successMessage);
      return result;
    } catch (err) {
      setNotice("");
      setError(err instanceof Error ? err.message : "Quote upload failed");
    } finally {
      setBusy(false);
    }
  }

  if (authStatus === "checking") return <ProductShell module="procurement" title="Procurement" navigation={[]}><SessionLoading/></ProductShell>;
  if (authStatus === "unauthenticated" || !user) return null;
  if (!overview) return <ProductShell module="procurement" title="Procurement" navigation={[]}>{error ? <section className="gg-session-loading"><div><AlertTriangle/><strong>Procurement could not load</strong><span>{error}</span><button className="gg-button primary" onClick={()=>void load({force:true})}>Try again</button></div></section> : <SessionLoading/>}</ProductShell>;
  const confirmedPostAction: PostAction = async (path, body, successMessage, version, method) => {
    const controlled = ['/publish', '/approve', '/dispatch', '/send', '/close', '/accept'];
    if (controlled.some((part) => path.includes(part))) {
      const effect = (successMessage ?? 'The selected workflow action will be completed').replace(/\.$/, '');
      const authority = roleLabel(user.role);
      if (!window.confirm('Confirm controlled action\n\n' + effect + '.\n\nYou are acting as ' + authority + '. This decision will be recorded in the audit ledger.')) return;
    }
    await postAction(path, body, successMessage, version, method);
  };

  const isAllowed = screenAllowed(overview, screen);
  const heading = isAllowed ? screenTitles[screen] : { crumb: "Workspace / Not assigned", title: "Not in your queue", subtitle: "This area is owned by another role. Your workspace only shows work you can act on." };

  const procurementHref: Record<string,string> = { control:"/procurement", procurement:"/procurement/requirements", approvals:"/procurement/approvals", rfq:"/procurement/rfqs", quotes:"/procurement/quotations", evidence:"/procurement/evidence", comparison:"/procurement/comparison", negotiations:"/procurement/negotiations", po:"/procurement/orders", inbound:"/procurement/inbound", gate:"/procurement/gate", store:"/procurement/store", quality:"/procurement/quality", invoices:"/procurement/invoices", cases:"/procurement/exceptions", outbox:"/procurement/outbox", integrations:"/procurement/integrations", audit:"/procurement/audit", admin:"/procurement/admin", setup:"/procurement/setup" };
  const sectionFor = (key:string) => key === "control" ? "Overview" : ["procurement","rfq","quotes","evidence","comparison","approvals","negotiations","po","invoices"].includes(key) ? "Procure" : ["inbound","gate","store","quality"].includes(key) ? "Receive" : "Manage";
  const productNav: ProductNavItem[] = overview.nav_items.filter(item=>item.key!=="agent").map(item=>({ label:item.label, href:procurementHref[item.key]??item.href, icon:navIconByKey[item.key]??Factory, section:sectionFor(item.key), badge:home?.badge_counts?.[item.key] }));
  return (
    <ProductShell module="procurement" navigation={productNav}>
      <main className="industrial-main">
        <header className="industrial-topbar">
          <div>
            <div className="crumb">{tower?.tenant_name ?? 'Workspace'} · {tower?.plant_name ?? 'Plant'}</div>
            <h1>{screen === 'control' ? `Good morning, ${user.name.split(' ')[0]}` : heading.title}</h1>
            <p>{screen === 'control' ? `${roleLabel(user.role)} · Focus on the work that needs you today.` : heading.subtitle}</p>
          </div>
          <div className="topbar-actions">
            {tower?.erp_mode === 'simulated' && <span className="erp-pill">Simulated ERP</span>}
          </div>
        </header>

        {user.role === 'purchase_executive' && <nav className="compact-procurement-nav" aria-label="Procurement shortcuts"><Link href="/procurement/requirements">Requirements</Link><Link href="/procurement/rfqs">RFQs</Link><Link href="/procurement/comparison">Comparison &amp; approvals</Link></nav>}
        {showSignInNotice && <div className="signed-banner"><span><BadgeCheck size={16} /> Signed in as {roleLabel(user.role)}.</span><button type="button" onClick={() => { signInNoticeExpiresAt = 0; setShowSignInNotice(false); }}>Dismiss</button></div>}
        {notice && <div className="signed-banner"><span><BadgeCheck size={16} /> {notice}</span><button type="button" onClick={() => setNotice("")}>Dismiss</button></div>}
        {error && <div className="error-banner">{error}</div>}

        <div className={`main-grid simplified-grid unified-companion-grid ${screen === 'control' ? 'dashboard-main-grid' : ''}`}>
          <section className="screen-stack">
            {isAllowed ? <>{screen !== 'control' && <SimpleWorkflowBar screen={screen} />}<ScreenBody screen={screen} overview={overview} home={home} myDay={myDay} tower={tower} workspaceData={workspaceData} user={user} postAction={confirmedPostAction} uploadQuoteAction={uploadQuoteAction} busy={busy} /></> : <NotInQueue overview={overview} />}
          </section>
        </div>
      </main>
    </ProductShell>
  );
}

function NotificationBell({ home, csrf }: { home: WorkspaceHome | null; csrf: string }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(home?.recent_notifications ?? []);
  useEffect(() => setRows(home?.recent_notifications ?? []), [home]);
  const unread = rows.filter((row) => asText(row.status) === 'unread').length;
  async function markRead(id: string) {
    await mutate('/notifications/' + encodeURIComponent(id) + '/read', csrf);
    setRows((current) => current.map((row) => asText(row.id) === id ? { ...row, status: 'read' } : row));
  }
  async function markAllRead() {
    await mutate('/notifications/read-all', csrf);
    setRows((current) => current.map((row) => ({ ...row, status: 'read' })));
  }
  return <div className="notification-menu"><button type="button" className="icon-button" aria-label="Notifications" aria-expanded={open} onClick={() => setOpen((value) => !value)}><Bell size={18} />{unread > 0 && <span>{unread > 99 ? '99+' : unread}</span>}</button>{open && <section className="notification-popover" aria-label="Notifications"><header><strong>Notifications</strong>{unread > 0 && <button type="button" onClick={() => void markAllRead()}>Mark all read</button>}</header><div>{rows.length ? rows.slice(0, 8).map((row) => <article key={asText(row.id)} className={asText(row.status) === 'unread' ? 'unread' : ''}><a href={asText(row.navigation_target, '/control-centre')} onClick={() => void markRead(asText(row.id))}><strong>{friendlyCopy(row.title)}</strong><span>{friendlyCopy(row.body)}</span><small>{asText(row.created_at) ? new Date(asText(row.created_at)).toLocaleString() : ''}</small></a></article>) : <p>No recent notifications.</p>}</div></section>}</div>;
}

function GroupedNavigation({ items, pathname, defaultRoute, badges = {} }: { items: WorkspaceOverview['nav_items']; pathname: string; defaultRoute: string; badges?: Record<string, number> }) {
  const groups = [
    { key: 'my_work', label: 'My work', keys: ['control'] },
    { key: 'procurement', label: 'Procurement', keys: ['procurement', 'rfq', 'quotes', 'evidence', 'comparison', 'approvals', 'negotiations', 'po', 'invoices'] },
    { key: 'inbound', label: 'Inbound', keys: ['inbound', 'gate', 'store', 'quality'] },
    { key: 'exceptions', label: 'Exceptions', keys: ['cases'] },
    { key: 'external', label: 'External delivery', keys: ['outbox'] },
    { key: 'administration', label: 'Administration', keys: ['setup', 'integrations', 'admin', 'audit'] },
  ];
  return <>{groups.map((group) => {
    const visible = items
      .filter((item) => group.keys.includes(item.key) && item.key !== 'agent')
      .filter((item, index, rows) => rows.findIndex(
        (candidate) => candidate.key === item.key && candidate.href === item.href,
      ) === index);
    if (!visible.length) return null;
    return <div className='nav-group' key={group.key}><div className='nav-group-label'>{group.label}</div>{visible.map((item) => {
      const Icon = navIconByKey[item.key] ?? Factory;
      const active = pathname === item.href || (pathname === '/' && item.href === defaultRoute);
      const count = badges[item.key] ?? (item.key === 'control' ? badges.my_work : 0) ?? 0;
      return <Link prefetch={false} className={'nav-link ' + (active ? 'active' : '')} href={item.href} key={`${item.key}:${item.href}`}><Icon size={15} /><span className="nav-link-label">{item.label}</span>{count > 0 && <span className="nav-badge">{count > 99 ? '99+' : count}</span>}</Link>;
    })}</div>;
  })}</>;
}

const simpleWorkflowSteps = [
  { key: 'procurement', label: '1. Requirement' },
  { key: 'rfq', label: '2. RFQ' },
  { key: 'quotes', label: '3. Quotations' },
  { key: 'comparison', label: '4. Compare & approve' },
  { key: 'po', label: '5. Purchase order' },
  { key: 'gate', label: '6. Gate & store' },
  { key: 'quality', label: '7. Quality' },
];

function SimpleWorkflowBar({ screen }: { screen: Screen }) {
  const aliases: Partial<Record<Screen, string>> = { approvals: 'comparison', evidence: 'quotes', store: 'gate', inbound: 'gate' };
  const active = aliases[screen] ?? screen;
  return <section className="simple-workflow-bar" aria-label="Procurement process">
    <div><span>One process</span><strong>Requirement to receipt</strong></div>
    <ol>{simpleWorkflowSteps.map((step) => <li className={step.key === active ? 'active' : ''} key={step.key}>{step.label}</li>)}</ol>
  </section>;
}


function TaskFirstOverview({ overview, user }: { overview: WorkspaceOverview; user: User }) {
  const primary = overview.work_items[0];
  const remaining = overview.work_items.slice(1);
  return <section className='task-first-home' aria-labelledby='next-work-title'>
    <div className='task-first-heading'>
      <div><div className='section-kicker'>{roleLabel(user.role)} workspace</div><h2 id='next-work-title'>What do I need to do next?</h2></div>
      <span className={'status-pill ' + (primary?.severity ?? 'good')}>{primary ? friendlyCopy(primary.status) : 'Queue clear'}</span>
    </div>
    {primary ? <div className='primary-work-item'>
      <div className='work-item-main'>
        <span className='dual-term'>{primary.plain_language_goal}</span>
        <h3>{friendlyCopy(primary.title)}</h3>
        <p>{friendlyCopy(primary.why_now)}</p>
        <dl className='work-item-facts'>
          <div><dt>What you need</dt><dd>{primary.required_evidence.join(', ') || 'The linked workflow record'}</dd></div>
          <div><dt>What happens next</dt><dd>{primary.expected_result}</dd></div>
          <div><dt>Who owns it</dt><dd>{roleLabel(primary.owner_role)}</dd></div>
          <div><dt>Due</dt><dd>{primary.due_at ? new Date(primary.due_at).toLocaleString() : 'No due date'}</dd></div>
        </dl>
      </div>
      <Link className='action-button open-task-button' href={primary.href}>Open task <ArrowRight size={16} /></Link>
    </div> : <div className='guided-empty'><BadgeCheck size={18} /><div><strong>Your queue is clear</strong><p>No action from this role is blocking the workflow. Check Waiting on others for the next handoff.</p></div></div>}
    <div className='queue-columns'>
      <WorkItemList title='My queue' items={remaining} />
      <HandoffQueue overview={overview} />
    </div>
  </section>;
}


function WorkItemList({ title, items }: { title: string; items: WorkItem[] }) {
  return <section className='queue-section'><div className='queue-head'><h3>{title}</h3><span>{items.length} remaining</span></div>
    <div className='compact-work-list'>{items.length ? items.map((item) => <Link href={item.href} className='compact-work-item' key={item.id}><div><strong>{item.plain_language_goal}</strong><small>{roleLabel(item.owner_role)}</small></div><ArrowRight size={15} /></Link>) : <p className='empty-state'>No additional work is assigned to you.</p>}</div>
  </section>;
}


const screenGuidance: Record<Screen, [string, string, string, string]> = {
  agent: ['Role agent workspace', 'Work with the assistant assigned to your membership and role.', 'Open assigned work, prepare a draft, or review a proposal.', 'You'],
  setup: ['Workspace readiness', 'Invite the operating team and prepare approved master data.', 'A synchronized procurement requirement can be created.', 'Workspace owner'],
  control: ['Team control', 'See work and risks across roles.', 'Open the role or exception blocking progress.', 'Plant Manager'],
  procurement: ['Material need (Requirement)', 'Record what the plant needs and by when.', 'A supplier request can be prepared.', 'Purchase Executive'],
  approvals: ['Human decision (Approval)', 'Review a frozen supplier comparison without editing commercial data.', 'Both named approvals allow the Purchase Manager to create the PO.', 'Plant Manager / Purchase Executive'],
  rfq: ['Ask suppliers for prices (RFQ)', 'Send one consistent request to approved suppliers.', 'Supplier offers can be received and reviewed.', 'Purchase Executive'],
  quotes: ['Supplier offer (Quotation)', 'Upload supplier documents and extract commercial information.', 'The offer moves to evidence verification.', 'Purchase Manager'],
  evidence: ['Review supplier offer (Quotation verification)', 'Check extracted values against the source document.', 'Only verified offers enter comparison.', 'Purchase Manager'],
  comparison: ['Compare suppliers (Bid comparison)', 'Compare landed cost, delivery, quality, compliance, and deviations.', 'A frozen version goes to two named approvers.', 'Purchase Manager'],
  negotiations: ['Improve terms (Negotiation)', 'Record controlled commercial discussions before comparison approval.', 'Changed quotes return to verification and comparison regeneration.', 'Purchase Manager'],
  po: ['Create the order (Purchase order)', 'Turn the dual-approved comparison into an immutable PO.', 'Supplier email and ERP posting remain separate.', 'Purchase Manager'],
  inbound: ['Track incoming material (Inbound)', 'Follow issued PO, gate, store, and quality events.', 'Received material becomes ready for inspection.', 'Gate / Store / Quality'],
  gate: ['Admit the delivery (Gate entry)', 'Match the vehicle and supplier challan to an issued PO.', 'Stores receives the admitted material for quantity entry.', 'Gate Operator'],
  store: ['Record received material (Store receipt)', 'Confirm quantity, shortage, and damage.', 'Quality receives an inspection task.', 'Store Manager'],
  quality: ['Check received material (Quality inspection)', 'Separate accepted, rejected, and held stock.', 'Inventory impact is recorded.', 'Quality Inspector'],
  invoices: ['Match supplier invoice', 'Compare invoice, order, and received quantity.', 'Prepare an evidence-backed finance review handoff.', 'Purchase Manager'],
  cases: ['Resolve a problem (Exception case)', 'Keep blockers visible and auditable.', 'The affected workflow can continue.', 'Assigned role'],
  outbox: ['External dispatch (Outbox)', 'Control approved email and ERP effects.', 'The external event is sent and reconciled.', 'Purchase Manager'],
  integrations: ['System connection (Integration)', 'Monitor ERP sync and reconciliation.', 'Local and external records remain aligned.', 'Admin'],
  audit: ['Decision history (Audit ledger)', 'Preserve accountability for every important action.', 'Authorized reviewers can trace the record.', 'Admin'],
  admin: ['Workspace setup (Administration)', 'Manage users, roles, plants, and agent policies.', 'Role queues remain correctly scoped.', 'Admin'],
};


function ContextGuide({ screen }: { screen: Screen }) {
  const [what, why, next, owner] = screenGuidance[screen];
  return <section className='context-guide' aria-label='Screen guidance'>
    <div><strong>What is this?</strong><span>{what}</span></div>
    <div><strong>Why is it here?</strong><span>{why}</span></div>
    <div><strong>What happens next?</strong><span>{next}</span></div>
    <div><strong>Who owns the next step?</strong><span>{owner}</span></div>
  </section>;
}


function ProcessRail({ overview }: { overview: WorkspaceOverview }) {
  const cycle = overview.cycles[0];
  return <aside className='workspace-rail'>
    {cycle && <section className='rail-card'><div className='rail-kicker'>Procure to receive</div><h2>{friendlyCopy(cycle.current_stage)}</h2><div className='rail-flow'>{cycle.stages.map((stage, index) => <Link href={(stage as unknown as { href?: string }).href ?? overview.default_route} className={'rail-stage ' + stage.status} key={stage.key}><span className='rail-stage-number'>{String(index + 1).padStart(2, '0')}</span><div><strong>{stage.label}</strong><small>{friendlyCopy(stage.summary ?? roleLabel(stage.owner_role ?? ''))}</small></div></Link>)}</div></section>}
    <section className='rail-card'><div className='rail-kicker'>Workflow handoff</div><ul className='rail-list'><li>{overview.work_items.length} action(s) in your queue</li><li>{overview.waiting_on.length} step(s) owned by another role</li><li>Opening a task never completes it</li></ul></section>
  </aside>;
}


function screenAllowed(overview: WorkspaceOverview, screen: Screen) {
  return overview.nav_items.some((item) => item.key === screenKeys[screen]);
}

function LoadingScreen() {
  return (
    <main className="loading-shell">
      <section className="loading-card">
        <div className="brand-block login-brand"><div className="brand-icon" aria-hidden="true">G</div><div><div className="brand-name">GenuineGigs</div><div className="brand-subtitle">Manufacturing Operations OS</div></div></div>
        <div className="crumb">OPERATIONS / SESSION CHECK</div>
        <h1>Restoring your control centre</h1>
        <p>Checking the secure session and loading plant workflow data.</p>
        <div className="loading-bar"><span /></div>
      </section>
    </main>
  );
}

function SessionLoading() {
  return <section className="gg-session-loading" role="status"><div><i/><strong>Opening Procurement</strong><span>Loading your assigned work and current supplier activity…</span></div></section>;
}

function LoginScreen({ email, setEmail, password, setPassword, workspaceOptions, workspaceMembershipId, setWorkspaceMembershipId, submitLogin, busy, error }: {
  email: string;
  setEmail: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  workspaceOptions: LoginWorkspaceOption[];
  workspaceMembershipId: string;
  setWorkspaceMembershipId: (value: string) => void;
  submitLogin: () => void;
  busy: boolean;
  error: string;
}) {
  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="brand-block login-brand"><div className="brand-icon" aria-hidden="true">G</div><div><div className="brand-name">GenuineGigs</div><div className="brand-subtitle">Manufacturing Operations OS</div></div></div>
        <div className="crumb">OPERATIONS / SECURE ACCESS</div>
        <h1>Sign in to GenuineGigs Operations OS</h1>
        <p>Sign in, choose your workspace, and continue to your plant command center.</p>
        <label>Email</label>
        <input aria-label='Email' value={email} onChange={(event) => setEmail(event.target.value)} type='email' autoComplete='email' />
        <details className='demo-account-picker'><summary>Use a development demo account</summary><div>{roleAccounts.map(([value, label]) => <button type='button' className='small-action' key={value} onClick={() => setEmail(value)}>{label}</button>)}</div></details>
        <label>Password</label>
        <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
        {workspaceOptions.length > 0 && <label>Workspace<select aria-label="Workspace" value={workspaceMembershipId} onChange={(event) => setWorkspaceMembershipId(event.target.value)}><option value="">Select workspace</option>{workspaceOptions.map((option) => <option value={option.membership_id} key={option.membership_id}>{option.workspace_name} · {option.plant_name} · {roleLabel(option.role)}</option>)}</select></label>}
        <button className="action-button wide" onClick={submitLogin} disabled={busy || (workspaceOptions.length > 0 && !workspaceMembershipId)}><LockKeyhole size={16} /> {busy ? "Signing in..." : workspaceOptions.length ? "Enter selected workspace" : "Continue"}</button>
        {error && <div className="error-banner">{error}</div>}
      </section>
      <aside className="login-rail">
        <div className="rail-kicker">One procurement process</div>
        <h2>Each role sees only the work it needs to complete.</h2>
        <ul><li>Requirement and RFQ</li><li>Quotation upload and extraction</li><li>Comparison and two approvals</li><li>PO, gate, store, and quality</li></ul>
      </aside>
    </main>
  );
}

function ScreenBody({ screen, overview, home, myDay, tower, workspaceData, user, postAction, uploadQuoteAction, busy }: {
  screen: Screen;
  overview: WorkspaceOverview;
  home: WorkspaceHome | null;
  myDay: MyDay | null;
  tower: ControlTowerSnapshot | null;
  workspaceData: WorkspaceData | null;
  user: User;
  postAction: PostAction;
  uploadQuoteAction: UploadAction;
  busy: boolean;
}) {
  if ((screen as Screen) === 'approvals') return <div className="approval-centre"><ActionQueue title="Decisions waiting for you" actions={overview.next_actions} postAction={postAction} busy={busy} /><ComparisonV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><ApprovalReviewPanel workspaceData={workspaceData} postAction={postAction} busy={busy} /></div>;
  switch (screen) {
    case "agent":
      return <AgentWorkspace workspaceData={workspaceData} user={user} />;
    case 'setup':
      return <WorkspaceSetupPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} />;
    case "control":
      return <><RoleHome overview={overview} home={home} myDay={myDay} user={user} postAction={postAction} busy={busy} /><ControlSummary tower={tower} /><Timeline tower={tower} /></>;
    case "procurement":
      return <><RequirementCreatePanel workspaceData={workspaceData} postAction={postAction} busy={busy} /><RequirementListPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /></>;
    case "approvals":
      return <><ActionQueue title="Pending approvals" actions={overview.next_actions} postAction={postAction} busy={busy} /><GenericTable title="Approval tasks" rows={workspaceData?.tasks ?? []} columns={["title", "entity_type", "owner_role", "status", "severity"]} /><GenericTable title="Award decisions" rows={workspaceData?.awards ?? []} columns={["id", "rfq_id", "supplier_id", "status", "approved_at"]} /><GenericTable title="PO drafts" rows={workspaceData?.po_drafts ?? []} columns={["id", "supplier_id", "status", "simulated_posting_correlation_id"]} /></>;
    case "rfq":
      return <SelectableRfqPanel workspaceData={workspaceData} postAction={postAction} busy={busy} />;
    case "quotes":
      return <><QuoteUploadPanel workspaceData={workspaceData} uploadQuoteAction={uploadQuoteAction} busy={busy} /><EvidenceReviewPanel workspaceData={workspaceData} postAction={postAction} busy={busy} /></>;
    case "evidence":
      return <EvidenceReviewPanel workspaceData={workspaceData} postAction={postAction} busy={busy} />;
    case "comparison":
      return <ComparisonV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} />;
    case "negotiations":
      return <NegotiationWorkflowPanel workspaceData={workspaceData} postAction={postAction} busy={busy} />;
    case "po":
      return <PoArtifactPanel workspaceData={workspaceData} postAction={postAction} busy={busy} />;
    case "inbound":
      return <><InboundV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><BusinessRecordCards title="Supplier acknowledgements" rows={workspaceData?.acknowledgements ?? []} queryKey="acknowledgement" href="/inbound" facts={["confirmed_quantity", "confirmed_delivery"]} /><BusinessRecordCards title="Arrivals at Gate" rows={workspaceData?.gate_entries ?? []} queryKey="gate" href="/inbound" facts={["vehicle_number", "supplier_challan"]} /><BusinessRecordCards title="Receipt and inspection status" rows={[...(workspaceData?.receipts ?? []), ...(workspaceData?.inspections ?? [])]} href="/inbound" facts={["received_quantity", "accepted_quantity", "rejected_quantity", "held_quantity"]} /></>;
    case "gate":
      return <><InboundV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><BusinessRecordCards title="Recent Gate entries" rows={workspaceData?.gate_entries ?? []} queryKey="gate" href="/gate" facts={["vehicle_number", "supplier_challan", "packages_count", "received_at"]} /><BusinessRecordCards title="Purchase orders expected at Gate" rows={workspaceData?.po_drafts ?? []} queryKey="po" href="/gate" facts={["approved_at"]} /></>;
    case "store":
      return <><InboundV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><SupplierReturnPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><BusinessRecordCards title="Store receipts" rows={workspaceData?.receipts ?? []} queryKey="receipt" href="/store" facts={["received_quantity", "short_quantity", "excess_quantity", "damaged_quantity", "exception_types", "certificate_status", "production_impact"]} /><BusinessRecordCards title="Arrivals waiting for Stores" rows={workspaceData?.gate_entries ?? []} queryKey="gate" href="/store" facts={["vehicle_number", "supplier_challan"]} /></>;
    case "quality":
      return <><InboundV2ActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><SupplierReturnPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><BusinessRecordCards title="Inspection results" rows={workspaceData?.inspections ?? []} queryKey="inspection" href="/quality" facts={["accepted_quantity", "rejected_quantity", "held_quantity", "certificate_status", "defect_codes", "production_impact"]} /><BusinessRecordCards title="Quality-controlled inventory impact" rows={workspaceData?.inventory_impact ?? []} href="/quality" facts={["usable_quantity", "rejected_quantity", "held_quantity"]} /></>;
    case "invoices":
      return <InvoiceMatchingPanel workspaceData={workspaceData} postAction={postAction} busy={busy} />;
    case "cases":
      return <><SupplierReturnPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><CaseResolutionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><CaseTable rows={workspaceData?.cases ?? tower?.cases ?? []} /></>;
    case "outbox":
      return <><OutboxControlPanel workspaceData={workspaceData} postAction={postAction} busy={busy} /><BusinessRecordCards title="Connected-system deliveries" rows={workspaceData?.erp_outbox ?? []} href="/outbox" queryKey="outbox" facts={["status", "last_error"]} /><BusinessRecordCards title="Supplier communications" rows={workspaceData?.email_outbox ?? []} href="/outbox" queryKey="outbox" facts={["recipient", "subject", "status", "sent_at"]} /></>;
    case "integrations":
      return <><IntegrationActionPanel workspaceData={workspaceData} postAction={postAction} busy={busy} /><IntegrationSummary workspaceData={workspaceData} /><GenericTable title="Supplier channel messages" rows={workspaceData?.supplier_messages ?? []} columns={["channel", "direction", "sender", "subject", "status"]} /><GenericTable title="Integration connections" rows={workspaceData?.connections ?? []} columns={["provider", "name", "status", "base_url"]} /><GenericTable title="ERP outbox and sync jobs" rows={[...(workspaceData?.outbox ?? []), ...(workspaceData?.sync_jobs ?? [])]} columns={["provider", "operation", "job_type", "status", "retry_count", "correlation_id"]} /></>;
    case "audit":
      return <GenericTable title="Append-only audit ledger" rows={workspaceData?.audit ?? []} columns={["actor", "action", "entity_type", "result"]} />;
    case "admin":
      return <><CompanionControls postAction={postAction} busy={busy} /><AutonomyCentre postAction={postAction} busy={busy} /><AdminManagementPanel workspaceData={workspaceData} postAction={postAction} busy={busy} /><MasterDataPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} /><AdminSummary workspaceData={workspaceData} user={user} postAction={postAction} busy={busy} /><GenericTable title="Users and guarded agents" rows={[...(workspaceData?.users ?? []), ...(workspaceData?.agents ?? [])]} columns={["name", "email", "role", "display_name", "allowed_actions", "blocked_actions"]} /></>;
  }
}

function CompanionControls({ postAction, busy }: { postAction: PostAction; busy: boolean }) {
  const [policies, setPolicies] = useState<Array<Record<string, unknown>>>([]);
  const [simulation, setSimulation] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { void apiFetch<Array<Record<string, unknown>>>("/admin/companion-trigger-policies").then(setPolicies).catch(() => setPolicies([])); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const id = crypto.randomUUID();
    await postAction(`/admin/companion-trigger-policies/${id}`, {
      name: String(data.get("name") || "Cycle preparation"), trigger_type: String(data.get("trigger_type") || "cycle.stage_changed"),
      roles: [String(data.get("role") || "purchase_executive")], minimum_severity: String(data.get("minimum_severity") || "info"),
      preparation_allowed: data.get("preparation_allowed") === "on", specialist_name: String(data.get("specialist_name") || "cycle_risk"),
      autonomy_ceiling: 1, delivery_mode: "risk_tiered", cooldown_seconds: 900, expiry_seconds: 86400,
    }, "Companion trigger saved.", undefined, "PUT");
    setPolicies(await apiFetch<Array<Record<string, unknown>>>("/admin/companion-trigger-policies"));
  }
  async function simulate() {
    const result = await mutate<Record<string, unknown>>("/admin/companion-trigger-policies/simulate", localStorage.getItem("gg_csrf") ?? "", { trigger_type: "cycle.stage_changed", role: "purchase_executive" });
    setSimulation(result);
  }
  return <section className="autonomy-centre companion-controls"><header><div><Bot size={20}/><div><h2>Companion controls</h2><p>Choose which events may proactively prepare work and how they reach each role.</p></div></div><span>Manual work always remains available</span></header><form onSubmit={save}><label>Policy name<input name="name" defaultValue="Prepare the next cycle step" required/></label><label>Trigger<select name="trigger_type"><option value="cycle.stage_changed">Cycle stage changed</option><option value="cycle.risk_changed">Cycle risk changed</option><option value="task.changed">Task or follow-up changed</option></select></label><label>Role<select name="role"><option value="purchase_executive">Purchase Executive</option><option value="purchase_manager">Purchase Manager</option><option value="plant_manager">Plant Manager</option></select></label><label>Specialist<select name="specialist_name"><option value="requirement_specification">Requirement review</option><option value="supplier_rfq">RFQ preparation</option><option value="quotation_normalization">Quotation review</option><option value="comparison_award">Comparison scenarios</option><option value="cycle_risk">Cycle risk</option></select></label><label>Minimum severity<select name="minimum_severity"><option>info</option><option>warning</option><option>critical</option></select></label><label className="autonomy-check"><input name="preparation_allowed" type="checkbox" defaultChecked/> Prepare eligible work in background</label><button className="action-button" disabled={busy}>Save trigger</button><button type="button" className="small-action" disabled={busy} onClick={() => void simulate()}>Simulate safe default</button></form>{simulation && <div className="policy-simulation"><strong>{simulation.matched ? "Published policy matched" : "Safe default matched"}</strong><span>{friendlyCopy(simulation.delivery_mode)} · {simulation.background_preparation ? "background preparation" : "manual only"} · {asText(simulation.policy_version)}</span></div>}<div className="autonomy-policy-list">{policies.length ? policies.map(policy => <article key={asText(policy.id)}><div><strong>{asText(policy.name)}</strong><small>{friendlyCopy(policy.trigger_type)} · {friendlyCopy(policy.specialist_name)}</small></div><span className={`policy-state ${asText(policy.state)}`}>{asText(policy.state)}</span>{policy.state === "draft" && <button className="small-action" disabled={busy} onClick={() => void postAction(`/admin/companion-trigger-policies/${asText(policy.id)}/publish`, undefined, "Companion trigger published.")}>Publish</button>}</article>) : <p>No custom trigger policy. Safe system defaults are active.</p>}</div></section>;
}

function AutonomyCentre({ postAction, busy }: { postAction: PostAction; busy: boolean }) {
  const [policies, setPolicies] = useState<Array<Record<string, unknown>>>([]);
  const [bundles, setBundles] = useState<Array<Record<string, unknown>>>([]);
  useEffect(() => { void Promise.all([apiFetch<Array<Record<string, unknown>>>('/admin/autonomy-policies'), apiFetch<Array<Record<string, unknown>>>('/admin/autonomy-policies/bundles')]).then(([nextPolicies, nextBundles]) => { setPolicies(nextPolicies); setBundles(nextBundles); }).catch(() => { setPolicies([]); setBundles([]); }); }, []);
  function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const id = crypto.randomUUID();
    void postAction(`/admin/autonomy-policies/${id}`, {
      name: String(data.get('name') || 'Coordination policy'), capability_id: String(data.get('capability_id') || 'delegate_task'),
      roles: [String(data.get('role') || 'purchase_manager')], autonomy_ceiling: Number(data.get('autonomy_ceiling') || 2),
      risk_limit: String(data.get('risk_limit') || 'low'), external_communication: String(data.get('external_communication') || 'confirm'),
      confirmation_required: data.get('confirmation_required') === 'on', plant_ids: [], category_ids: [],
    }, 'Autonomy policy draft saved.', undefined, 'PUT').then(() => apiFetch<Array<Record<string, unknown>>>('/admin/autonomy-policies').then(setPolicies));
  }
  return <section className="autonomy-centre"><header><div><ShieldCheck size={20}/><div><h2>Autonomy centre</h2><p>Publish scoped policy templates without exposing raw Rego.</p></div></div><span>OPA policy decisions are independently audited</span></header><form onSubmit={createDraft}><label>Policy name<input name="name" defaultValue="Low-risk internal coordination" required /></label><label>Capability<input name="capability_id" defaultValue="delegate_task" required /></label><label>Role<select name="role" defaultValue="purchase_manager"><option value="purchase_manager">Purchase Manager</option><option value="plant_manager">Plant Manager</option><option value="purchase_executive">Purchase Executive</option></select></label><label>Autonomy ceiling<select name="autonomy_ceiling" defaultValue="2"><option value="0">Tier 0 · Observe</option><option value="1">Tier 1 · Prepared work</option><option value="2">Tier 2 · Coordination</option><option value="3">Tier 3 · Reversible execution</option><option value="4">Tier 4 · Human confirmation</option></select></label><label>Risk limit<select name="risk_limit"><option>low</option><option>medium</option><option>high</option></select></label><label>External communication<select name="external_communication"><option value="confirm">Require confirmation</option><option value="deny">Deny</option></select></label><label className="autonomy-check"><input name="confirmation_required" type="checkbox" defaultChecked /> Human confirmation required</label><button className="action-button" disabled={busy}>Save draft</button></form><div className="autonomy-policy-list">{policies.length ? policies.map(policy => <article key={asText(policy.id)}><div><strong>{asText(policy.name)}</strong><small>{asText(policy.capability_id)} · tier {asText(policy.autonomy_ceiling)}</small></div><span className={`policy-state ${asText(policy.state)}`}>{asText(policy.state)}</span>{policy.state === 'draft' && <button className="small-action" disabled={busy} onClick={() => void postAction(`/admin/autonomy-policies/${asText(policy.id)}/publish`, undefined, 'Policy published.')}>Publish</button>}</article>) : <p>No autonomy templates have been created.</p>}</div>{bundles.length > 0 && <details className="policy-bundles"><summary>Signed policy bundles and rollback</summary>{bundles.map(bundle => <article key={asText(bundle.id)}><div><strong>{asText(bundle.bundle_version)}</strong><small>Digest {asText(bundle.digest).slice(0, 12)}… · {asText(bundle.state)}</small></div>{bundle.state !== 'active' && <button className="small-action" disabled={busy} onClick={() => void postAction(`/admin/autonomy-policies/bundles/${asText(bundle.id)}/activate`, undefined, 'Verified policy bundle activated.')}>Activate rollback</button>}</article>)}</details>}</section>;
}


function QuoteUploadPanel({ workspaceData, uploadQuoteAction, busy }: { workspaceData: WorkspaceData | null; uploadQuoteAction: UploadAction; busy: boolean }) {
  const rfqs = workspaceData?.rfqs ?? [];
  const suppliers = workspaceData?.suppliers ?? [];
  const [rfqId, setRfqId] = useRouteSelection("rfq");
  const rfq = rfqs.find((row) => rowId(row) === rfqId);
  const rfqSupplierIds = arrayText(rfq?.supplier_ids);
  const [mode, setMode] = useState<"parsed" | "manual">("parsed");
  const [intake, setIntake] = useState<QuotationIntake | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (mode === "parsed") form.set("intake_mode", "parsed");
    const result = await uploadQuoteAction(
      form,
      mode === "parsed" ? "Quotation uploaded. Extraction is running." : "Manual quotation saved; the PDF comparison is running in the background.",
    );
    if (mode === "parsed" && result) setIntake(result as QuotationIntake);
  }
  useEffect(() => {
    if (!intake || !["queued", "extracting"].includes(intake.status)) return;
    const timer = window.setInterval(() => {
      void getQuotationIntake(intake.id).then(setIntake).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [intake]);
  async function acceptParsed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!intake) return;
    const form = new FormData(event.currentTarget);
    const firstLine = intake.fields.lines?.[0] ?? {};
    const fields = {
      ...intake.fields,
      quote_number: form.get("quote_number"),
      quote_date: form.get("quote_date"),
      validity_date: form.get("validity_date"),
      payment_terms: form.get("payment_terms"),
      currency: form.get("currency"),
      lines: [{
        ...firstLine,
        quantity: Number(form.get("quantity")),
        uom: form.get("uom"),
        unit_price: Number(form.get("unit_price")),
        gst_rate: Number(form.get("gst_rate") || 0),
        freight: Number(form.get("freight") || 0),
        packaging: Number(form.get("packaging") || 0),
        lead_time_days: Number(form.get("lead_time_days") || 0),
        promised_date: form.get("promised_date"),
        moq: Number(form.get("moq") || form.get("quantity")),
      }],
    };
    await mutate(`/procurement/quotation-intakes/${intake.id}/accept`, localStorage.getItem("gg_csrf") || "", {
      supplier_id: form.get("supplier_id"),
      fields,
    }, "POST", intake.version);
    setIntake(null);
    window.location.reload();
  }
  const parsedLine = intake?.fields.lines?.[0] ?? {};
  const field = (name: string, fallback = "") => asText(intake?.fields[name] ?? fallback);
  const lineField = (name: string, fallback = "") => asText(parsedLine[name] ?? intake?.fields[name] ?? fallback);
  return (
    <section className="action-panel workflow-action-panel">
      <div className="panel-head compact-head"><div><div className="section-kicker">Quotation intake</div><h3>Add supplier quotation</h3></div><span className="record-count">PDF / image / XLSX</span></div>
      <div className="button-row">
        <button type="button" className={mode === "parsed" ? "action-button" : "small-action"} onClick={() => setMode("parsed")}>Upload and extract</button>
        <button type="button" className={mode === "manual" ? "action-button" : "small-action"} onClick={() => setMode("manual")}>Enter details manually</button>
      </div>
      <form className="ops-form" onSubmit={submit}>
        <label>RFQ<select name="rfq_id" value={rfqId} onChange={(event) => setRfqId(event.target.value)} required><option value="">Select RFQ</option>{rfqs.map((item) => <option value={asText(item.id)} key={asText(item.id)}>{asText(item.business_number ?? item.id)} / {friendlyCopy(item.status)}</option>)}</select></label>
        {mode === "manual" && <>
          <label>Supplier<select name="supplier_id" defaultValue="" required><option value="" disabled>Select supplier</option>{suppliers.length ? suppliers.map((supplier) => <option value={asText(supplier.id)} key={asText(supplier.id)}>{friendlyCopy(supplier.name ?? supplier.id)}</option>) : rfqSupplierIds.map((supplierId) => <option value={supplierId} key={supplierId}>{friendlyCopy(supplierId)}</option>)}</select></label>
          <label>Quote no.<input name="quote_number" placeholder="QTN-2451" required /></label>
          <label>Currency<input name="currency" defaultValue="INR" maxLength={16} required /></label>
          <label>Quantity<input name="quantity" type="number" min="0.01" step="0.01" required /></label>
          <label>Unit price<input name="unit_price" type="number" min="0" step="0.01" required /></label>
          <label>GST %<input name="gst_rate" type="number" step="0.01" defaultValue="18" /></label>
          <label>Freight<input name="freight" type="number" step="0.01" defaultValue="0" /></label>
          <label>Lead time days<input name="lead_time_days" type="number" defaultValue="7" /></label>
          <label className="span-2">Certificates<input name="certificates" placeholder="MTC, COA, RoHS" /></label>
        </>}
        <label className="span-2">Quotation file<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx,image/*,application/pdf" required /></label>
        <button className="action-button" disabled={busy || !rfq} type="submit">{mode === "parsed" ? "Upload and extract details" : "Save manual quotation"}</button>
      </form>
      {intake && <div className="quotation-review-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setIntake(null); }}><section className="action-panel quotation-review-dialog" role="dialog" aria-modal="true" aria-label="Review extracted quotation">
        <div className="panel-head compact-head"><div><div className="section-kicker">Extraction review</div><h3>{intake.document?.filename}</h3></div><span className="record-count">{friendlyCopy(intake.status)}</span></div>
        {["queued", "extracting"].includes(intake.status) ? <p>LlamaParse is reading the document. This review updates automatically.</p> :
          <form className="ops-form" onSubmit={acceptParsed} key={`${intake.id}-${intake.version}`}>
            <label>Supplier<select name="supplier_id" defaultValue={intake.supplier_id ?? ""} required><option value="">Select supplier</option>{suppliers.map((supplier) => <option value={asText(supplier.id)} key={asText(supplier.id)}>{friendlyCopy(supplier.name ?? supplier.id)}</option>)}</select></label>
            <label>Quote no.<input name="quote_number" defaultValue={field("quote_number")} required /></label>
            <label>Quote date<input name="quote_date" type="date" defaultValue={field("quote_date")} required /></label>
            <label>Valid until<input name="validity_date" type="date" defaultValue={field("validity_date")} required /></label>
            <label>Payment terms<input name="payment_terms" defaultValue={field("payment_terms", "30 days from GRN")} /></label>
            <label>Currency<input name="currency" defaultValue={field("currency", "INR")} required /></label>
            <label>Quantity<input name="quantity" type="number" min="0.01" step="0.01" defaultValue={lineField("quantity")} required /></label>
            <label>UOM<input name="uom" defaultValue={lineField("uom")} /></label>
            <label>Unit price<input name="unit_price" type="number" min="0" step="0.01" defaultValue={lineField("unit_price")} required /></label>
            <label>GST %<input name="gst_rate" type="number" step="0.01" defaultValue={lineField("gst_rate", "0")} /></label>
            <label>Freight<input name="freight" type="number" step="0.01" defaultValue={lineField("freight", "0")} /></label>
            <label>Packaging<input name="packaging" type="number" step="0.01" defaultValue={lineField("packaging", "0")} /></label>
            <label>Lead time days<input name="lead_time_days" type="number" defaultValue={lineField("lead_time_days", "0")} /></label>
            <label>Promised date<input name="promised_date" type="date" defaultValue={lineField("promised_date")} /></label>
            <label>MOQ<input name="moq" type="number" step="0.01" defaultValue={lineField("moq")} /></label>
            <div className="span-2"><small>Parser: {friendlyCopy(intake.parser.provider)}. Extracted values remain unverified until you accept them.</small></div>
            <button className="action-button" type="submit" disabled={busy}>Accept quotation</button>
            <button className="small-action" type="button" onClick={() => setIntake(null)}>Cancel review</button>
          </form>}
      </section></div>}
    </section>
  );
}

function PoGeneratorPanel({ workspaceData, postAction, busy }: { workspaceData: WorkspaceData | null; postAction: PostAction; busy: boolean }) {
  const awards = workspaceData?.awards ?? [];
  const poDrafts = workspaceData?.po_drafts ?? [];
  const [awardId, setAwardId] = useRouteSelection("award");
  const [poId, setPoId] = useRouteSelection("po");
  const approvedAward = awards.find((row) => rowId(row) === awardId);
  const po = poDrafts.find((row) => rowId(row) === poId);
  return (
    <section className="action-panel workflow-action-panel">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">PO generator</div><h3>Generate and approve purchase order</h3></div>
        <div className="button-row">
          <button className="small-action" disabled={busy || !awardId || String(approvedAward?.status) !== "approved"} onClick={() => { void postAction("/procurement/po-drafts", { award_id: awardId }, "PO draft generated from approved award."); }}>Generate PO</button>
          <button className="small-action" disabled={busy || !poId || ["approved_pending_outbox", "simulated_posted", "posted"].includes(String(po?.status))} onClick={() => { void postAction("/procurement/po-drafts/" + poId + "/approve", undefined, "PO approved. ERP outbox event awaits separate approval.", typeof po?.version === "number" ? po.version : undefined); }}>Approve PO</button>
        </div>
      </div>
      <div className="workflow-form-grid">
        <label>Approved award<select value={awardId} onChange={(event) => setAwardId(event.target.value)}><option value="">Select award</option>{awards.map((award) => <option value={rowId(award)} key={rowId(award)}>{asText(award.business_number ?? award.id)} / {friendlyCopy(award.status)}</option>)}</select></label>
        <label>PO draft<select value={poId} onChange={(event) => setPoId(event.target.value)}><option value="">Select PO</option>{poDrafts.map((draft) => <option value={rowId(draft)} key={rowId(draft)}>{asText(draft.business_number ?? draft.id)} / {friendlyCopy(draft.status)}</option>)}</select></label>
        <div className="quick-record"><span>Approved award</span><strong>{awardId || "No approved award"}</strong><small>Supplier: {friendlyCopy(approvedAward?.supplier_id)}</small></div>
        <div className="quick-record"><span>PO draft</span><strong>{poId || "Not generated yet"}</strong><small>Status: {friendlyCopy(po?.status ?? "Generate after award approval")}</small></div>
        <div className="quick-record"><span>ERP posting</span><strong>{asText(po?.simulated_posting_correlation_id, "Pending")}</strong><small>Oracle/SAP/local outbox remains approval controlled</small></div>
      </div>
    </section>
  );
}

function RoleHome({ overview, home, myDay, user, postAction, busy }: { overview: WorkspaceOverview; home: WorkspaceHome | null; myDay: MyDay | null; user: User; postAction: PostAction; busy: boolean }) {
  const [focused, setFocused] = useState<ProcurementCycleSummary | null>(null);
  const cycles = home?.cycles ?? [];
  const actions = [...(home?.actionable_work_items ?? [])].sort((a, b) => actionPriority(a, cycles) - actionPriority(b, cycles));
  const attention = home?.attention_items.length ?? 0;
  const overdue = actions.filter(item => item.due_state.toLowerCase().includes('overdue')).length;
  const blockers = cycles.filter(isActuallyBlocked).length;
  const completed = cycles.filter(cycle => cycle.completion_percentage === 100).length;
  const stats = [
    { label: 'Needs your attention', value: attention, detail: 'Decisions and blockers', tone: 'danger' as const, icon: AlertTriangle },
    { label: 'Assistant prepared', value: home?.assistant_prepared.length ?? 0, detail: 'Ready for your review', tone: 'assistant' as const, icon: Bot },
    { label: 'My tasks', value: home?.my_tasks.length ?? actions.length, detail: 'Assigned to you', tone: 'task' as const, icon: ClipboardCheck },
    { label: 'Waiting on others', value: home?.waiting_on_others.length ?? 0, detail: 'Across your team', tone: 'waiting' as const, icon: Users },
  ];
  return <div className="work-dashboard">
    <section className="operations-brief" aria-label="Today’s operations brief"><div className="brief-icon"><ClipboardCheck size={19} /></div><div><strong>Today’s operations brief</strong><p>{actions.length} active assignment{actions.length === 1 ? '' : 's'} <i /> {overdue} overdue <i /> {blockers} blocker{blockers === 1 ? '' : 's'} <i /> {completed} completed cycle{completed === 1 ? '' : 's'}</p></div><small>Live workspace data</small><button type="button" aria-label="Refresh dashboard" disabled={busy} onClick={() => window.dispatchEvent(new Event('genuinegigs:refresh'))}>Refresh</button></section>
    <section className="dashboard-kpis" aria-label="Work summary">{stats.map(stat => <KPIStatCard key={stat.label} {...stat} />)}</section>
    <MyDayBand data={myDay} />
    {['plant_manager', 'purchase_manager', 'admin'].includes(user.role) && <ManagerCockpit />}
    <div className="work-dashboard-columns"><div className="work-dashboard-primary">
      <section className="dashboard-panel cycle-list-panel" aria-labelledby="active-cycles-title"><DashboardSectionHeader title="Active procurement cycles" count={cycles.length} linkLabel="View all cycles" /><div className="procurement-cycle-list">{cycles.length ? cycles.slice(0, 8).map(cycle => <ProcurementCycleRow key={cycle.id} cycle={cycle} userRole={user.role} onOpen={() => setFocused(cycle)} />) : <DashboardEmpty title="No active procurement cycles" detail="New material requirements will appear here as soon as they enter the workflow." />}</div></section>
      <section className="dashboard-panel priority-queue" aria-labelledby="priority-queue-title"><DashboardSectionHeader title="Priority action queue" count={actions.length} linkLabel="View full queue" /><div className="action-queue-grid">{actions.length ? actions.slice(0, 6).map(item => <ActionQueueCard key={item.id} item={item} blocked={isActuallyBlocked(cycles.find(cycle => cycle.id === item.cycle.id))} />) : <DashboardEmpty title="Your priority queue is clear" detail="No authorized action is currently holding a procurement cycle." />}</div></section>
    </div></div>
    {focused && <CycleFocusDrawer cycle={focused} durable={myDay?.cycles.find(row => row.requirement_id === focused.id)} onClose={() => setFocused(null)} />}
  </div>;
}

function ManagerCockpit() {
  const [operations, setOperations] = useState<Record<string, unknown> | null>(null);
  const [exceptions, setExceptions] = useState<Array<Record<string, unknown>>>([]);
  useEffect(() => { void Promise.all([apiFetch<Record<string, unknown>>('/manager/operations'), apiFetch<Array<Record<string, unknown>>>('/manager/exceptions')]).then(([nextOperations, nextExceptions]) => { setOperations(nextOperations); setExceptions(nextExceptions); }).catch(() => { setOperations(null); setExceptions([]); }); }, []);
  const health = (operations?.cycle_health ?? {}) as Record<string, number>;
  return <section className="manager-cockpit" aria-labelledby="manager-cockpit-title"><header><div><h2 id="manager-cockpit-title">Operations cockpit</h2><p>Factual cycle health and interventions across your reporting scope.</p></div><Link href="/agent">Open delegation console</Link></header><div className="manager-health">{['on_track','attention','at_risk','blocked'].map(state => <div key={state}><span>{friendlyCopy(state)}</span><strong>{health[state] ?? 0}</strong></div>)}</div><div className="manager-exceptions"><h3>Exception queue</h3>{exceptions.length ? exceptions.slice(0, 5).map((exception, index) => { const task = (exception.task ?? {}) as Record<string, unknown>; return <article key={String(task.id ?? index)}><div><strong>{asText(task.title, 'Operational exception')}</strong><small>{asText(exception.current_owner, 'Owner pending')} · {asText(exception.impact, 'normal')} impact</small></div><p>{asText(exception.recommended_intervention, 'Review supporting evidence')}</p></article>; }) : <p>No reporting-scope exception requires intervention.</p>}</div></section>;
}

function MyDayBand({ data }: { data: MyDay | null }) {
  const groups = [
    ['Decisions required', data?.decisions_required ?? [], 'decision'],
    ['Prepared for you', data?.prepared_for_you ?? [], 'prepared'],
    ['Do now', data?.do_now ?? [], 'now'],
    ['Waiting on others', data?.waiting_on_others ?? [], 'waiting'],
    ['Watching', data?.watching ?? [], 'watching'],
    ['At risk', data?.at_risk ?? [], 'risk'],
    ['Completed today', data?.completed_today ?? [], 'complete'],
  ] as const;
  return <section className="my-day-band" aria-labelledby="my-day-heading">
    <header><div><h2 id="my-day-heading">My Day</h2><p>Prepared work, decisions, dependencies, and risks in one operational view.</p></div><span>{groups.reduce((total, [, rows]) => total + rows.length, 0)} visible items</span></header>
    <div className="my-day-groups">{groups.map(([label, records, tone]) => <article className={`my-day-group ${tone}`} key={label}><div><strong>{label}</strong><span>{records.length}</span></div>{records.length ? <ul>{records.slice(0, 3).map((record, index) => { const row = record as Record<string, unknown>; const evaluation = row.evaluation as Record<string, unknown> | undefined; return <li key={String(row.id ?? index)}><strong>{asText(row.title ?? row.business_number ?? row.presentation_stage, label)}</strong><small>{asText(row.status ?? evaluation?.production_risk ?? row.health, 'Ready for review')}</small></li>; })}</ul> : <p>Nothing here right now.</p>}</article>)}</div>
  </section>;
}

function isActuallyBlocked(cycle?: ProcurementCycleSummary) { return Boolean(cycle && cycle.current_stage.status === 'blocked' && cycle.blocked_dependency); }
function actionPriority(item: ActionableWorkItem, cycles: ProcurementCycleSummary[]) { return isActuallyBlocked(cycles.find(cycle => cycle.id === item.cycle.id)) ? 0 : item.due_state.toLowerCase().includes('overdue') ? 1 : item.due_state.toLowerCase().includes('soon') ? 2 : 3; }

function DashboardSectionHeader({ title, count, linkLabel }: { title: string; count: number; linkLabel: string }) { return <header className="dashboard-section-header"><div><h2>{title}</h2><span>{count} {count === 1 ? 'item' : 'items'}</span></div><Link href="/procurement">{linkLabel}</Link></header>; }

function DashboardEmpty({ title, detail }: { title: string; detail: string }) { return <div className="dashboard-empty"><BadgeCheck size={21} /><div><strong>{title}</strong><p>{detail}</p></div></div>; }

function KPIStatCard({ label, value, detail, tone, icon: Icon }: { label: string; value: number; detail: string; tone: 'danger' | 'assistant' | 'task' | 'waiting'; icon: typeof AlertTriangle }) { return <article className={`kpi-stat-card ${tone}`}><span><Icon size={20} /></span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>; }

const dashboardStages = [
  ['requirement', 'Requirement'], ['rfq', 'RFQ'], ['quotes', 'Quotations'], ['comparison', 'Comparison'], ['approval', 'Approval'], ['po', 'PO'], ['invoice', 'Invoice'],
] as const;

function dashboardStageStatus(cycle: ProcurementCycleSummary, key: string, index: number) {
  if (key === 'approval') {
    const comparison = cycle.stages.find(stage => stage.key === 'comparison');
    return comparison?.status === 'done' ? 'done' : comparison?.status === 'current' ? 'current' : 'waiting';
  }
  if (key === 'invoice') return cycle.completion_percentage === 100 ? 'current' : 'waiting';
  const direct = cycle.stages.find(stage => stage.key === key);
  if (isActuallyBlocked(cycle) && index === Math.max(0, cycle.current_stage_index - 1)) return 'blocked';
  return direct?.status ?? 'waiting';
}

function CycleStageTracker({ cycle }: { cycle: ProcurementCycleSummary }) { return <div className="cycle-stage-scroller"><ol className="cycle-stage-tracker" aria-label={`Procurement progress: ${cycle.current_stage.label}`}>{dashboardStages.map(([key,label], index) => { const status = dashboardStageStatus(cycle,key,index); return <li className={status} key={key} aria-current={status === 'current' ? 'step' : undefined}><span>{status === 'done' ? <BadgeCheck size={13} /> : index + 1}</span><small>{label}</small></li>; })}</ol></div>; }

function StatusBadge({ cycle }: { cycle: ProcurementCycleSummary }) { const state = isActuallyBlocked(cycle) ? 'blocked' : cycle.health === 'at_risk' ? 'at_risk' : cycle.health === 'attention' || cycle.health === 'blocked' ? 'attention' : 'on_track'; const label = state === 'blocked' ? 'Blocked' : state === 'at_risk' ? 'At risk' : state === 'attention' ? 'Action needed' : cycle.current_stage.status === 'current' ? 'In progress' : 'On track'; return <span className={`dashboard-status ${state}`}>{label}</span>; }

function ProcurementCycleRow({ cycle, userRole, onOpen }: { cycle: ProcurementCycleSummary; userRole: string; onOpen: () => void }) {
  const route = cycle.role_visible_actions[0];
  const owned = cycle.next_owner === userRole || userRole === 'admin';
  const allowed = Boolean(route && owned);
  const cta = cycle.current_stage.key === 'comparison' ? 'Review comparison' : cycle.current_stage.key === 'po' ? 'Approve purchase order' : cycle.current_stage.key === 'quotes' ? 'Review quotations' : `Continue ${cycle.current_stage.label}`;
  const owner = roleLabel(cycle.next_owner);
  const blocked = isActuallyBlocked(cycle);
  return <article className={`procurement-cycle-row ${blocked ? 'blocked' : cycle.health}`} tabIndex={0} role="button" onClick={onOpen} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onOpen(); } }}><div className="cycle-record"><span className="cycle-record-icon"><Factory size={18} /></span><div><small>{cycle.rfqs[0]?.business_number ?? cycle.business_number}</small><strong>{cycle.materials[0]?.label ?? cycle.title}</strong><p>{cycle.materials[0]?.secondary_context ?? 'Material requirement'} <i /> {cycle.business_number}</p></div></div><div className="cycle-progress"><CycleStageTracker cycle={cycle} /><div className="cycle-handoff"><span>Current owner: <strong>{owner}</strong></span><span>{blocked ? 'Blocked by' : 'Awaiting'}: <strong>{blocked ? cycle.blocked_dependency : cycle.current_stage.summary ?? cycle.next_stage ?? 'Completion'}</strong></span></div></div><div className="cycle-row-action"><StatusBadge cycle={cycle} /><small className={cycle.health === 'at_risk' || blocked ? 'urgent' : ''}>{cycle.need_by_date ? `Due ${new Date(`${cycle.need_by_date}T00:00:00`).toLocaleDateString()}` : 'No due date'}</small>{allowed ? <Link className="cycle-cta permitted" href={route!} onClick={event => event.stopPropagation()}><BadgeCheck size={14} /> {cta}</Link> : <div className="cycle-authority"><span><LockKeyhole size={13} /> Waiting on {owner}</span><small>No action available for your role</small><button type="button" onClick={event => { event.stopPropagation(); onOpen(); }}>View cycle details</button></div>}</div></article>;
}

function ActionQueueCard({ item, blocked }: { item: ActionableWorkItem; blocked: boolean }) { const urgent = blocked || item.due_state.toLowerCase().includes('overdue'); const allowed = item.allowed_actions.length > 0; return <article className={`action-queue-card ${urgent ? 'urgent' : ''}`}><div className="action-card-icon">{urgent ? <AlertTriangle size={17} /> : <FileText size={17} />}</div><div className="action-card-body"><strong>{friendlyCopy(item.title)}</strong><small>{item.cycle.business_number} <i /> {item.material?.label ?? item.cycle.label}</small><p>{blocked && item.blocker ? item.blocker : `Review the evidence required for ${item.stage_label.toLowerCase()}.`}</p><footer><span>{item.current_owner}</span><span className={urgent ? 'urgent' : ''}>{item.due_state}</span></footer></div>{allowed ? <Link className="cycle-cta permitted" href={item.primary_route}>{item.allowed_actions[0]}</Link> : <span className="queue-waiting"><LockKeyhole size={12} /> Waiting on {item.current_owner}</span>}</article>; }

function CycleMatrix({ cycles }: { cycles: ProcurementCycleSummary[] }) {
  return <section className="cycle-matrix"><div><span>Portfolio matrix</span><h2>Where work is concentrating</h2></div><div className="matrix-scroll"><table><thead><tr><th>Material cycle</th>{['Need','RFQ','Quotes','Compare','PO','Gate','Receipt','Inspect'].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{cycles.map(cycle => <tr key={cycle.id}><th><strong>{cycle.materials[0]?.label ?? cycle.title}</strong><small>{cycle.business_number}</small></th>{cycle.stages.map(stage => <td key={stage.key}><span className={stage.status} title={`${stage.label}: ${stage.summary ?? stage.status}`} /></td>)}</tr>)}</tbody></table></div></section>;
}

function CycleFocusDrawer({ cycle, durable, onClose }: { cycle: ProcurementCycleSummary; durable?: DurableProcurementCycle; onClose: () => void }) {
  const [timeline, setTimeline] = useState<Array<Record<string, unknown>>>([]);
  useEffect(() => { const close = (event: KeyboardEvent) => event.key === 'Escape' && onClose(); window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, [onClose]);
  useEffect(() => { if (!durable) return; void apiFetch<Array<Record<string, unknown>>>(`/procurement/cycles/${durable.id}/timeline`).then(setTimeline).catch(() => setTimeline([])); }, [durable]);
  const blocked = isActuallyBlocked(cycle);
  const health = blocked ? 'Blocked' : cycle.health === 'at_risk' ? 'At risk' : cycle.health === 'attention' || cycle.health === 'blocked' ? 'Action needed' : 'On track';
  return <div className="cycle-drawer-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}><aside className="cycle-drawer" role="dialog" aria-modal="true" aria-labelledby="cycle-drawer-title"><header><div><span>{cycle.business_number}</span><h2 id="cycle-drawer-title">{cycle.materials[0]?.label ?? cycle.title}</h2><p>{cycle.materials[0]?.secondary_context} · needed {cycle.need_by_date ?? 'date not set'}</p></div><button onClick={onClose} aria-label="Close cycle details">Close</button></header><div className="drawer-stage-list">{cycle.stages.map((stage,index) => <article className={stage.status} key={stage.key}><i>{index + 1}</i><div><strong>{stage.label}</strong><p>{stage.summary}</p><small>{roleLabel(stage.owner_role ?? '')}</small></div></article>)}</div><section className="drawer-context"><div><small>Current owner</small><strong>{roleLabel(cycle.next_owner)}</strong></div><div><small>Health</small><strong>{health}</strong></div><div><small>Next stage</small><strong>{cycle.next_stage ?? 'Cycle complete'}</strong></div>{blocked && <div><small>Blocked by</small><strong>{cycle.blocked_dependency}</strong></div>}</section>{durable && <section className="drawer-intelligence"><h3>Dependencies, evidence and prepared work</h3>{durable.dependencies.map(row => <article key={row.id}><strong>Dependency · {row.type}</strong><p>{row.description}</p></article>)}{durable.risks.map(row => <article className="risk" key={row.id}><strong>{friendlyCopy(row.severity)} risk</strong><p>{row.summary}</p><small>{row.evidence.length} evidence reference(s)</small></article>)}{durable.prepared_work.map(row => <article className="prepared" key={row.id}><strong>{row.title}</strong><p>{friendlyCopy(row.type)} · {Math.round(row.confidence * 100)}% confidence</p><small>{row.evidence.length} evidence reference(s)</small></article>)}{!durable.dependencies.length && !durable.risks.length && !durable.prepared_work.length && <p>No unresolved dependency, risk, or prepared item.</p>}<details><summary>Correlated timeline ({timeline.length})</summary>{timeline.map(row => <p key={asText(row.id)}><strong>{friendlyCopy(row.event_type)}</strong> · {asText(row.created_at)}</p>)}</details></section>}<footer>{cycle.role_visible_actions[0] ? <Link className="action-button" href={cycle.role_visible_actions[0]}>Continue current stage <ArrowRight size={16} /></Link> : <p>Waiting on {roleLabel(cycle.next_owner)}. No action is available for your role at this stage.</p>}</footer></aside></div>;
}

function WorkflowCycleCard({ cycle }: { cycle: WorkspaceOverview["cycles"][number] }) {
  return (
    <section className="workflow-card">
      <div className="workflow-head">
        <div>
          <div className="section-kicker">Purchase cycle</div>
          <h3>{friendlyCopy(cycle.title)}</h3>
          <p>{friendlyCopy(cycle.subtitle)}</p>
        </div>
        <div className={"cycle-severity " + cycle.severity}>{cycle.due_label}</div>
      </div>
      <div className="stage-track">
        {cycle.stages.map((stage) => (
          <div className={"stage-node " + stage.status} key={stage.key}>
            <div className="stage-dot" />
            <strong>{stage.label}</strong>
            <span>{friendlyCopy(stage.summary ?? roleLabel(stage.owner_role ?? ""))}</span>
          </div>
        ))}
      </div>
      <div className="stage-legend"><span className="done">Done</span><span className="current">Current</span><span className="blocked">Blocked</span><span className="waiting">Waiting</span></div>
      <div className="cycle-next"><strong>Next step:</strong><span>{friendlyCopy(cycle.next_step)}</span></div>
    </section>
  );
}

function ActionQueue({ title, actions, postAction, busy }: { title: string; actions: NextAction[]; postAction: PostAction; busy: boolean }) {
  const visible = actions.length ? actions : [];
  const destinations: Record<string, [string, string]> = {
    supplier_quotes: ['/evidence', 'quote'], rfqs: ['/rfq-builder', 'rfq'],
    award_decisions: ['/approvals', 'award'], po_drafts: ['/po-drafts', 'po'],
    negotiation_rounds: ['/negotiations', 'negotiation'], cases: ['/cases', 'case'],
    store_receipts: ['/store', 'receipt'], inspection_results: ['/quality', 'inspection'],
    outbox_messages: ['/outbox', 'outbox'],
  };
  return <section className='action-panel'><div className='panel-head compact-head'><div><div className='section-kicker'>My work</div><h3>{title}</h3></div><span className='record-count'>{visible.length} open</span></div>
    <div className='action-list'>{visible.length ? visible.map((action) => {
      const [route, key] = destinations[action.entity_type ?? ''] ?? ['/cases', 'task'];
      const href = route + '?' + key + '=' + encodeURIComponent(action.entity_id ?? action.id);
      return <div className={'action-card ' + action.severity} key={action.id}><div><strong>{friendlyCopy(action.title)}</strong><p>{friendlyCopy(action.description)}</p><span className='action-help'>{roleLabel(action.role)} owns this step</span></div><Link className='small-action' href={href}>Open task <ArrowRight size={14} /></Link></div>;
    }) : <p className='empty-state'>No open actions for this role. Check Waiting on others for the next handoff.</p>}</div>
  </section>;
  return (
    <section className="action-panel">
      <div className="panel-head compact-head"><div><div className="section-kicker">Command queue</div><h3>{title}</h3></div><span className="record-count">{visible.length} open</span></div>
      <div className="action-list">
        {visible.length ? visible.map((action) => (
          <div className={"action-card " + action.severity} key={action.id}>
            <div>
              <strong>{friendlyCopy(action.title)}</strong>
              <p>{friendlyCopy(action.description)}</p>
              <span className="action-help">{roleLabel(action.role)} owns this step</span>
            </div>
            <button className="small-action" disabled={busy || !action.path} onClick={() => { if (action.path) void postAction(action.path, action.body ?? undefined, actionLabel(action) + " completed. Workspace refreshed.", action.version); }}>{actionLabel(action)} <ArrowRight size={14} /></button>
          </div>
        )) : <p className="empty-state">No open actions for this role.</p>}
      </div>
    </section>
  );
}

function HandoffQueue({ overview }: { overview: WorkspaceOverview }) {
  return (
    <section className="action-panel">
      <div className="panel-head compact-head"><div><div className="section-kicker">Waiting on</div><h3>Cross-role handoffs</h3></div><span className="record-count">{overview.waiting_on.length}</span></div>
      <div className="action-list">
        {overview.waiting_on.length ? overview.waiting_on.slice(0, 5).map((action) => (
          <div className="handoff-card" key={action.id}>
            <strong>{roleLabel(action.role)}</strong>
            <div><span>{friendlyCopy(action.title)}</span><small>{friendlyCopy(action.description)}</small></div>
          </div>
        )) : <p className="empty-state">No handoffs are blocking this queue.</p>}
      </div>
    </section>
  );
}

function WorkspaceRail({ overview, postAction, busy }: { overview: WorkspaceOverview; postAction: PostAction; busy: boolean }) {
  const cycle = overview.cycles[0];
  const primary = overview.next_actions[0];
  return (
    <aside className="workspace-rail">
      <section className="rail-card rail-next-action">
        <div className="rail-kicker">Next for you</div>
        <h2>{primary ? friendlyCopy(primary.title) : "Nothing waiting"}</h2>
        <p>{primary ? friendlyCopy(primary.description) : "This role is not blocking the workflow right now."}</p>
        {primary?.path ? <button className="small-action" disabled={busy} onClick={() => { void postAction(primary.path as string, primary.body ?? undefined, actionLabel(primary) + " completed. Workspace refreshed.", primary.version); }}>{actionLabel(primary)} <ArrowRight size={14} /></button> : <span className="status-pill good">Queue clear</span>}
      </section>
      {cycle && <section className="rail-card"><div className="rail-kicker">Procure to receive</div><div className="rail-flow">{cycle.stages.map((stage, index) => <div className={"rail-stage " + stage.status} key={stage.key}><span className="rail-stage-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{stage.label}</strong><small>{friendlyCopy(stage.summary ?? roleLabel(stage.owner_role ?? ""))}</small></div></div>)}</div></section>}
      <section className="rail-card"><div className="rail-kicker">Role workload</div>{overview.team_workload.length ? <WorkloadBars overview={overview} /> : <ul className="rail-list"><li>{overview.next_actions.length} action in your queue</li><li>{overview.waiting_on.length} handoff outside your role</li><li>{cycle?.current_stage ?? "Cycle"} is active</li></ul>}</section>
    </aside>
  );
}

function WorkloadBars({ overview }: { overview: WorkspaceOverview }) {
  return <div className="workload-bars">{overview.team_workload.map((bar) => <div className="workload-row" key={bar.label}><div><strong>{bar.label}</strong><span>{bar.value} open</span></div><div className="workload-track"><span className={bar.tone} style={{ width: Math.min(100, Math.round((bar.value / Math.max(1, bar.total)) * 100)) + "%" }} /></div></div>)}</div>;
}

function NotInQueue({ overview }: { overview: WorkspaceOverview }) {
  return <section className="panel access-panel"><div className="panel-head"><div><div className="section-kicker">Not in your queue</div><h3>This screen belongs to another role</h3></div><Link className="small-action" href={overview.default_route}>Go to my work</Link></div><p>Your workspace hides controls you cannot act on. If you need visibility, use the screens listed in your left navigation.</p></section>;
}

function ControlSummary({ tower }: { tower: ControlTowerSnapshot | null }) {
  const metrics = [
    { label: "Open cases", value: tower?.open_cases ?? 0, tone: "critical" },
    { label: "Approvals", value: tower?.pending_approvals ?? 0, tone: "action" },
    { label: "Supplier issues", value: tower?.supplier_exceptions ?? 0, tone: "action" },
    { label: "ERP mode", value: friendlyCopy(tower?.erp_mode ?? "simulated"), tone: "good" }
  ];
  return <section className="control-summary" aria-label="Control centre summary">{metrics.map((item) => <div className={"summary-tile " + item.tone} key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</section>;
}

function CaseTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  return <GenericTable title="Connected recovery queue" eyebrow="Dispatch + purchasing + inbound" rows={rows} columns={["requirement", "supplier", "owner_role", "due_label", "value_label", "status"]} />;
}

function ComparisonTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  return <GenericTable title="Supplier bid comparison" eyebrow="Deterministic gates before recommendation" rows={rows} columns={["supplier", "landed_cost_label", "delivery_status", "quality_score_label", "commercial_terms", "decision", "disqualification_reason"]} />;
}

function IntegrationSummary({ workspaceData }: { workspaceData: WorkspaceData | null }) {
  return (
    <section className="control-summary" aria-label="Integration summary">
      <div className="summary-tile good"><span>ERP connections</span><strong>{workspaceData?.connections?.length ?? 0}</strong></div>
      <div className="summary-tile action"><span>Sync jobs</span><strong>{workspaceData?.sync_jobs?.length ?? 0}</strong></div>
      <div className="summary-tile action"><span>Outbox events</span><strong>{workspaceData?.outbox?.length ?? 0}</strong></div>
      <div className="summary-tile good"><span>Mode</span><strong>Local</strong></div>
    </section>
  );
}

function AdminSummary({ workspaceData, user, postAction, busy }: { workspaceData: WorkspaceData | null; user: User; postAction: PostAction; busy: boolean }) {
  const readiness = workspaceData?.readiness?.[0] ?? {};
  const analytics = workspaceData?.analytics?.[0] ?? {};
  const checks = arrayRows(readiness.checks);
  const metrics = arrayRows(analytics.metrics);
  const policies = workspaceData?.procurement_policies ?? [];
  function createPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const minimumQuotes = Number(form.get('minimum_quotes') || 1);
    const highValueAmount = Number(form.get('high_value_amount') || 0);
    const highValueQuotes = Number(form.get('high_value_quotes') || minimumQuotes);
    void postAction('/procurement/policies', {
      name: form.get('name'),
      rules: {
        minimum_quotation_count: minimumQuotes,
        quotation_thresholds: highValueAmount > 0 ? [{ minimum_amount: highValueAmount, count: highValueQuotes }] : [],
        allowed_currencies: asText(form.get('allowed_currencies'), 'INR').split(',').map((value) => value.trim().toUpperCase()).filter(Boolean),
        require_unexpired_quotes: form.get('require_unexpired_quotes') === 'on',
        allow_split_awards: form.get('allow_split_awards') === 'on',
        require_single_source_justification: true,
        segregation: { requester_cannot_submit_comparison: form.get('segregation') === 'on' },
        approval_matrix: [{ minimum_amount: 0, roles: ['plant_manager', 'purchase_executive'] }],
      },
    }, 'Procurement policy draft created for review.');
  }
  function activatePolicy(policy: Record<string, unknown>) {
    void postAction(`/procurement/policies/${rowId(policy)}/activate`, { confirmation: 'ACTIVATE_POLICY' }, 'Procurement policy activated. Earlier policy versions were retired.', typeof policy.version === 'number' ? policy.version : undefined);
  }
  return (
    <><section className="action-panel workflow-action-panel">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Admin controls</div><h3>Workspace controls</h3></div>
        <button className="small-action danger" disabled={busy || user.role !== "admin"} onClick={() => { void postAction("/admin/reset-workspace", { confirmation: "RESET" }); }}>Reset workspace data</button>
      </div>
      <div className="action-list"><p className="empty-state">{(workspaceData?.users?.length ?? 0)} users and {(workspaceData?.agents?.length ?? 0)} guarded agents are configured.</p></div>
      <div className="panel-head compact-head"><div><div className="section-kicker">Customer readiness</div><h3>{asText(readiness.percent, "0")}% configured</h3><p>Measured from persisted configuration, not demo activity.</p></div><a className="secondary-button" href={apiUrl('/workspace/configuration-export')} target="_blank" rel="noreferrer">Export configuration</a></div>
      <div className="setup-checklist">{checks.map((check) => <div className={check.ready ? 'done' : ''} key={asText(check.key)}><span aria-hidden="true">{check.ready ? '✓' : '○'}</span><strong>{asText(check.label)}</strong><Link href={asText(check.evidence_href, '/workspace/setup')}>Review</Link></div>)}</div>
      <div className="panel-head compact-head"><div><div className="section-kicker">Evidence-linked operations</div><h3>Management metrics</h3><p>No opaque employee score is generated.</p></div></div>
      <div className="business-card-grid">{metrics.map((metric) => <article className="business-record-card" key={asText(metric.key)}><div><strong>{asText(metric.label)}</strong><span>{metric.value === null || metric.value === undefined ? 'Not yet measurable' : `${asText(metric.value)} ${asText(metric.unit)}`}</span><small>{asText(metric.sample_size, '0')} source records</small>{metric.note ? <p>{asText(metric.note)}</p> : null}</div><Link className="small-action" href={asText(metric.evidence_href, '/audit')}>View evidence</Link></article>)}</div>
    </section>
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Deterministic purchasing rules</div><h3>Procurement policy</h3><p>The assistant can explain these rules, but only the server evaluates and enforces them.</p></div><span className="record-count">{policies.length} versions</span></div>
      <form className="ops-form" onSubmit={createPolicy}><label>Policy name<input name="name" defaultValue="Plant purchasing policy" required /></label><label>Minimum quotations<input name="minimum_quotes" type="number" min="1" defaultValue="1" required /></label><label>High-value threshold<input name="high_value_amount" type="number" min="0" step="0.01" defaultValue="500000" /></label><label>Quotations above threshold<input name="high_value_quotes" type="number" min="1" defaultValue="3" /></label><label>Allowed currencies<input name="allowed_currencies" defaultValue="INR" required /></label><label className="checkbox-label"><input name="require_unexpired_quotes" type="checkbox" defaultChecked /> Require current quote validity</label><label className="checkbox-label"><input name="allow_split_awards" type="checkbox" defaultChecked /> Allow split awards</label><label className="checkbox-label"><input name="segregation" type="checkbox" /> Requester cannot submit comparison</label><button className="action-button" disabled={busy}>Create policy draft</button></form>
      <div className="business-card-grid">{policies.map((policy) => <article className="business-record-card" key={rowId(policy)}><div><strong>{asText(policy.name)}</strong><span>Version {asText(policy.policy_version)} · {friendlyCopy(policy.status)}</span><span className={`status-pill ${asText(policy.status) === 'active' ? 'good' : 'neutral'}`}>{friendlyCopy(policy.status)}</span></div>{asText(policy.status) === 'draft' && <button className="small-action" disabled={busy} onClick={() => activatePolicy(policy)}>Activate policy</button>}</article>)}</div>
    </section></>
  );
}

function Timeline({ tower }: { tower: ControlTowerSnapshot | null }) {
  return <section className="panel"><div className="panel-head"><div><div className="section-kicker">Case timeline</div><h3>Material need to receipt / inspection exception</h3></div></div><div className="timeline-list">{(tower?.timeline ?? []).map((event, index) => <div className="timeline-item" key={asText(event.title) + "-" + index}><span>{asText(event.occurred_at_label)}</span><strong>{asText(event.title)}</strong><p>{asText(event.body)}</p></div>)}</div></section>;
}

function actionLabel(action: NextAction) {
  if (action.entity_type === "supplier_quotes") return "Verify quote";
  if (action.entity_type === "award_decisions") return "Approve award";
  if (action.entity_type === "outbox_messages") return "Send email";
  if (action.entity_type === "store_receipts") return "Record receipt";
  if (action.entity_type === "inspection_results") return "Record inspection";
  if (action.entity_type === "cases") return "Create follow-up";
  if (action.entity_type === "rfqs") return "Review and send";
  if (action.entity_type === "po_drafts") return "Approve PO";
  if (action.entity_type === "negotiation_rounds") return "Approve negotiation";
  return "Start action";
}


function arrayText(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function rowId(row: Record<string, unknown> | undefined | null) {
  return typeof row?.id === "string" ? row.id : "";
}

function arrayRows(value: unknown) {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : [];
}

function comparisonRows(workspaceData: WorkspaceData | null, tower: ControlTowerSnapshot | null) {
  const active = workspaceData?.active_cycle?.[0] as unknown as { rfqs?: Array<Record<string, unknown>> } | undefined;
  const fromCycle = (active?.rfqs ?? []).flatMap((rfq) => arrayRows(rfq.comparison_rows).map((row) => ({ ...row, rfq_id: rowId(rfq) })));
  return fromCycle.length ? fromCycle : tower?.quote_comparison ?? [];
}

const friendlyValues: Record<string, string> = {
  "item-rm-304": MATERIAL_NAME,
  "RM-304": MATERIAL_NAME,
  "RM-304 material commitment recovery": MATERIAL_NAME + " commitment recovery",
  "RM-304 EN8 round bar shortage for SO-1042": MATERIAL_NAME + " shortage for packaging line rebuild",
  "RM-304 EN8 round bar shortage": MATERIAL_NAME + " shortage",
  "EN8 round bar": MATERIAL_NAME,
  "SO-1042": "packaging line rebuild",
  "SLEEVE-A": MATERIAL_NAME,
  "sup-steel-01": "Apex Alloy Works",
  "sup-steel-02": "Bharat Metals",
  "sup-steel-03": "Crown Industrial Supply"
};

const columnLabels: Record<string, string> = {
  item_id: "Material",
  supplier_id: "Supplier",
  supplier_ids: "Suppliers",
  requirement_id: "Material request",
  po_draft_id: "Purchase order",
  receipt_id: "Receipt",
  owner_role: "Owner",
  due_label: "Due",
  value_label: "Value",
  need_by_date: "Need by",
  quote_number: "Quote ref",
  parser_version: "Parser",
  model_version: "Review model",
  verification_status: "Verification",
  revised_unit_price: "Revised unit price",
  oracle_mapping: "ERP mapping",
  exception_types: "Exceptions",
  certificate_status: "Certificate",
  production_impact: "Production impact",
  defect_codes: "Defects"
};

function GenericTable({ title, eyebrow, rows, columns }: { title: string; eyebrow?: string; rows: Array<Record<string, unknown>>; columns: string[] }) {
  return <section className="panel"><div className="panel-head"><div><div className="section-kicker">{eyebrow ?? "Operational ledger"}</div><h3>{title}</h3></div><span className="record-count">{rows.length} records</span></div><GenericInner rows={rows} columns={columns} /></section>;
}

function BusinessRecordCards({ title, rows, href, queryKey, facts }: {
  title: string;
  rows: Array<Record<string, unknown>>;
  href: string;
  queryKey?: string;
  facts: string[];
}) {
  return <section className="panel business-record-panel">
    <div className="panel-head"><div><div className="section-kicker">Operational status</div><h3>{title}</h3></div><span className="record-count">{rows.length}</span></div>
    <div className="business-record-list">{rows.length ? rows.map((row, index) => {
      const recordId = rowId(row);
      const displayId = asText(row.business_number ?? row.quote_number ?? row.title, "");
      const material = row.item_id ? friendlyCopy(displayValue("item_id", row.item_id, row)) : "";
      const target = queryKey && recordId ? `${href}?${queryKey}=${encodeURIComponent(recordId)}` : href;
      return <article className="business-record-row" key={recordId || `${title}-${index}`}>
        <span className="business-record-icon"><FileText size={17} /></span>
        <div className="business-record-copy">
          <div><strong>{displayId || material || title.replace(/s$/, "")}</strong><span className={`business-status ${asText(row.status)}`}>{friendlyCopy(row.status ?? "recorded")}</span></div>
          {material && displayId && <p>{material}</p>}
          <dl>{facts.filter((field) => row[field] !== null && row[field] !== undefined && row[field] !== "").map((field) => <div key={field}><dt>{columnLabel(field)}</dt><dd>{friendlyCopy(displayValue(field, row[field], row))}</dd></div>)}</dl>
        </div>
        <Link className="small-action" href={target}>Open</Link>
      </article>;
    }) : <div className="ledger-empty">No records yet. This section updates when the previous role completes its handoff.</div>}</div>
  </section>;
}

function GenericInner({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  const schemas = columns.map((key) => ({
    key,
    label: columnLabel(key),
    width: key === 'oracle_mapping' ? 360 : key.includes('correlation') ? 220 : key === 'status' ? 150 : key.includes('id') ? 180 : 160,
    mono: key.includes('hash') || key.includes('quantity') || key.includes('cost') || key.includes('price') || key.includes('correlation'),
  }));
  return <div className='table-wrap' role='region' aria-label='Scrollable operational records' tabIndex={0}><table className='industrial-table schema-table'><colgroup>{schemas.map((schema) => <col key={schema.key} style={{ width: schema.width }} />)}</colgroup><thead><tr>{schemas.map((schema) => <th key={schema.key}>{schema.label}</th>)}</tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={[asText(row.id, String(index)), index].join('-')}>{schemas.map((schema) => <td key={schema.key} data-label={schema.label} className={schema.mono ? 'mono' : ''}>{structuredCell(displayValue(schema.key, row[schema.key], row))}</td>)}</tr>) : <tr><td colSpan={columns.length} className='ledger-empty'>No records yet. This ledger will fill when the previous workflow step is completed.</td></tr>}</tbody></table></div>;
  return <div className="table-wrap"><table className="industrial-table"><thead><tr>{columns.map((column) => <th key={column}>{columnLabel(column)}</th>)}</tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={[asText(row.id, String(index)), index].join("-")}>{columns.map((column) => <td key={column} className={column.includes("hash") || column.includes("quantity") || column.includes("cost") || column.includes("price") ? "mono" : ""}>{cell(displayValue(column, row[column], row))}</td>)}</tr>) : <tr><td colSpan={columns.length}>No records loaded yet.</td></tr>}</tbody></table></div>;
}


function TaskDelegationPanel({ overview, postAction, busy }: {
  overview: WorkspaceOverview;
  postAction: PostAction;
  busy: boolean;
}) {
  if (!overview.delegation_targets.length) return null;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const dueValue = String(data.get('due_at') ?? '');
    void postAction('/tasks', {
      title: String(data.get('title') ?? ''),
      requested_outcome: String(data.get('requested_outcome') ?? ''),
      assignee_membership_id: String(data.get('assignee_membership_id') ?? ''),
      priority: String(data.get('priority') ?? 'normal'),
      due_at: dueValue ? new Date(dueValue).toISOString() : null,
    }, 'Task delegated. It is now visible in the assignee queue.');
    event.currentTarget.reset();
  }
  return <section className='action-panel task-delegation-panel'>
    <div className='panel-head compact-head'>
      <div><div className='section-kicker'>Team coordination</div><h3>Delegate a task</h3></div>
      <span className='record-count'>Reporting tree only</span>
    </div>
    <form className='ops-form' onSubmit={submit}>
      <label>Task title<input name='title' required minLength={3} placeholder='Verify quotations for RFQ-014' /></label>
      <label>Assignee<select name='assignee_membership_id' required defaultValue=''>
        <option value='' disabled>Select employee</option>
        {overview.delegation_targets.map((target) => <option value={target.membership_id} key={target.membership_id}>{target.name} / {roleLabel(target.role)}</option>)}
      </select></label>
      <label>Due date<input name='due_at' type='datetime-local' /></label>
      <label>Priority<select name='priority' defaultValue='normal'><option value='normal'>Normal</option><option value='high'>High</option><option value='urgent'>Urgent</option></select></label>
      <label className='full-span'>Requested outcome<textarea name='requested_outcome' required minLength={3} rows={3} placeholder='Describe the evidence-backed result expected from the assignee.' /></label>
      <div className='button-row full-span'><button className='primary-button' type='submit' disabled={busy}>Delegate task</button></div>
    </form>
  </section>;
}


function TaskLifecyclePanel({ overview, postAction, busy }: {
  overview: WorkspaceOverview;
  postAction: PostAction;
  busy: boolean;
}) {
  const active = overview.work_items.filter((item) => ['open', 'accepted', 'in_progress', 'blocked', 'review'].includes(item.status));
  if (!active.length) return null;
  const nextStatus = (status: string) => status === 'open' ? 'accepted' : status === 'accepted' || status === 'blocked' ? 'in_progress' : status === 'in_progress' ? 'review' : null;
  return <section className='action-panel task-lifecycle-panel'>
    <div className='panel-head compact-head'><div><div className='section-kicker'>My tasks</div><h3>Execution queue</h3></div><span className='record-count'>{active.length} active</span></div>
    <div className='task-lifecycle-list'>{active.map((item) => {
      const target = nextStatus(item.status);
      return <article key={item.id}>
        <div><strong>{item.title}</strong><span>{friendlyCopy(item.status)} / {roleLabel(item.owner_role)}</span><small>{item.due_at ? new Date(item.due_at).toLocaleString() : 'No due date'}</small></div>
        <div className='button-row'><Link className='secondary-button' href={item.href}>Open context</Link>{target && <button className='primary-button' type='button' disabled={busy} onClick={() => void postAction('/tasks/' + encodeURIComponent(item.id) + '/transition', { status: target }, 'Task moved to ' + friendlyCopy(target) + '.')}>{target === 'accepted' ? 'Accept' : target === 'in_progress' ? 'Start work' : 'Submit for review'}</button>}</div>
      </article>;
    })}</div>
  </section>;
}


function structuredCell(value: unknown) {
  if (Array.isArray(value)) return <span className='list-cell'>{value.map((item) => friendlyCopy(item)).join(', ')}</span>;
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>);
    return <details className='object-details'><summary>{entries.length} mapped fields</summary><dl>{entries.slice(0, 12).map(([key, item]) => <div key={key}><dt>{columnLabel(key)}</dt><dd>{friendlyCopy(item)}</dd></div>)}</dl></details>;
  }
  return cell(value);
}

function columnLabel(column: string) {
  return columnLabels[column] ?? column.replaceAll("_", " ");
}

function displayValue(column: string, value: unknown, row: Record<string, unknown>) {
  if (column === "id") return row.title ?? row.requirement ?? row.subject ?? row.name ?? row.quote_number ?? friendlyCopy(value);
  if (column === "item_id") return MATERIAL_NAME;
  if (column === "supplier_ids" && Array.isArray(value)) return value.map((item) => friendlyCopy(item));
  if (Array.isArray(value)) return value.map((item) => friendlyCopy(item)).join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value;
}

function friendlyText(value: unknown) {
  if (typeof value === 'object' && value !== null) return '';
  const text = asText(value);
  return friendlyValues[text] ?? text;
}

function friendlyCopy(value: unknown) {
  let text = friendlyText(value);
  const replacements: Array<[string, string]> = [
    ["RM-304 material commitment recovery", MATERIAL_NAME + " commitment recovery"],
    ["RM-304 EN8 round bar shortage for SO-1042", MATERIAL_NAME + " shortage for packaging line rebuild"],
    ["RM-304 EN8 round bar shortage", MATERIAL_NAME + " shortage"],
    ["EN8 round bar", MATERIAL_NAME],
    ["RM-304", MATERIAL_NAME],
    ["SO-1042", "packaging line rebuild"]
  ];
  replacements.forEach(([from, to]) => {
    text = text.replaceAll(from, to);
  });
  return text;
}

function firstBusinessCopy(...values: unknown[]) {
  for (const value of values) {
    if (typeof value !== 'string' && typeof value !== 'number') continue;
    const text = friendlyCopy(value).trim();
    if (text && text !== '{}' && text !== '[]' && text !== '-') return text;
  }
  return '';
}

function cell(value: unknown) {
  if (Array.isArray(value)) return <span className="list-cell">{value.map((item) => friendlyCopy(item)).join(", ")}</span>;
  if (typeof value === "object" && value !== null) {
    return <span className="object-cell">{Object.entries(value as Record<string, unknown>).slice(0, 8).map(([key, item]) => <span key={key}><strong>{columnLabel(key)}</strong>{friendlyCopy(item)}</span>)}</span>;
  }
  const text = friendlyCopy(value);
  if (["critical", "blocked", "rejected", "disqualified"].some((word) => text.toLowerCase().includes(word))) return <span className="status-pill critical">{text}</span>;
  if (["pending", "approval", "drafted", "waiting", "action"].some((word) => text.toLowerCase().includes(word))) return <span className="status-pill action">{text}</span>;
  if (["approved", "posted", "sent", "accepted", "closed", "complete", "verified"].some((word) => text.toLowerCase().includes(word))) return <span className="status-pill good">{text}</span>;
  return text || "-";
}
