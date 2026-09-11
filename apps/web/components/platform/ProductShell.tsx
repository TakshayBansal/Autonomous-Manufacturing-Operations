"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell, Boxes, BriefcaseBusiness, ChevronDown, CircleHelp, Factory, FileWarning, Gavel, Home, LogOut, Menu,
  PackageSearch, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Settings, Sparkles, X,
} from "lucide-react";
import { commandGigiInsight, getGigiInsights, getPlatformAppContext, mutate, type PlatformModuleKey } from "@/lib/api";
import { GigiPanel } from "@/components/platform/GigiPanel";

export type ProductNavItem = { label: string; href: string; icon?: typeof Home; badge?: number; section?: string };

type ShellModule = PlatformModuleKey | "home" | "cases" | "work" | "decisions";
const globalModules: Array<{ key: ShellModule; label: string; href: string; icon: typeof Home }> = [
  { key: "home", label: "Command Center", href: "/home", icon: Home },
  { key: "cases", label: "Cases", href: "/cases", icon: FileWarning },
  { key: "work", label: "My Work", href: "/operations/my-work", icon: BriefcaseBusiness },
  { key: "decisions", label: "Decisions", href: "/decisions", icon: Gavel },
  { key: "procurement", label: "Procurement", href: "/procurement", icon: PackageSearch },
  { key: "scm", label: "SCM", href: "/scm", icon: Boxes },
  { key: "operations", label: "Operations", href: "/operations", icon: Factory },
  { key: "platform", label: "Administration", href: "/admin", icon: Settings },
];

export function ProductShell({ module, navigation, children, title, onRefresh, wide = false }: {
  module: ShellModule;
  navigation: ProductNavItem[];
  children: React.ReactNode;
  title?: string;
  onRefresh?: () => Promise<void> | void;
  wide?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const context = useQuery({ queryKey: ["platform-app-context"], queryFn: getPlatformAppContext, retry: false });
  const insights = useQuery({ queryKey: ["gigi-insights"], queryFn: getGigiInsights, retry: false, refetchInterval: 30000 });
  const [localCollapsed, setLocalCollapsed] = useState(wide);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [gigiOpen, setGigiOpen] = useState(false);
  const [gigiView, setGigiView] = useState<"ask"|undefined>();
  const profileRef = useRef<HTMLDivElement>(null);
  const available = useMemo(
    () => new Set(context.data?.modules.filter(item => item.enabled).map(item => item.key) ?? []),
    [context.data?.modules],
  );
  const searchable = useMemo(() => [
    ...globalModules.filter(item => ["home","cases","work","decisions"].includes(item.key) || available.has(item.key as PlatformModuleKey)),
    ...navigation.map(item => ({ ...item, key: module })),
  ].filter(item => item.label.toLowerCase().includes(query.toLowerCase())), [available, module, navigation, query]);

  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); setSearchOpen(true);
      }
      if (event.key === "Escape") { setSearchOpen(false); setNotificationsOpen(false); }
    };
    window.addEventListener("keydown", shortcut);
    const openGigi = (event: Event) => { setGigiView((event as CustomEvent<{view?:string}>).detail?.view === "ask" ? "ask" : undefined); setGigiOpen(true); };
    window.addEventListener("genuinegigs:open-gigi", openGigi);
    window.addEventListener("v2:open-gigi", openGigi);
    window.addEventListener("genuinegigs:open-companion", openGigi);
    return () => { window.removeEventListener("keydown", shortcut); window.removeEventListener("genuinegigs:open-gigi", openGigi); window.removeEventListener("v2:open-gigi", openGigi); window.removeEventListener("genuinegigs:open-companion", openGigi); };
  }, []);

  async function refresh() {
    if (refreshing) return;
    setRefreshing(true);
    try { await onRefresh?.(); await client.invalidateQueries(); router.refresh(); }
    finally { window.setTimeout(() => setRefreshing(false), 450); }
  }
  async function logout() {
    const csrf = localStorage.getItem("gg_csrf") ?? "";
    try { if (csrf) await mutate("/auth/logout", csrf); }
    finally { localStorage.removeItem("gg_csrf"); router.replace("/login"); router.refresh(); }
  }
  const user = context.data?.user;
  const openInsights = insights.data?.filter(item => !["RESOLVED", "DISMISSED", "ACKNOWLEDGED"].includes(item.delivery_state) && !item.acknowledged_at && !item.dismissed_at && (!item.snoozed_until || new Date(item.snoozed_until).getTime() <= Date.now())) ?? [];
  const activeInsight = openInsights.find(item => item.delivery_state === "POPUP");
  const companionState = insights.isError || insights.isPending ? "unknown" : activeInsight ? "urgent" : openInsights.length ? "watching" : "quiet";
  const initials = user?.name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase() ?? "GG";
  const shellTitle = title ?? (module === "home" ? "Home" : module === "scm" ? "Supply Chain" : module[0].toUpperCase() + module.slice(1));
  const hasLocalNavigation = navigation.length > 0;

  return <div className={`gg-product-shell gg-module-${module} ${module === "scm" ? "scm-shell" : ""} ${localCollapsed ? "gg-local-collapsed" : ""} ${hasLocalNavigation ? "" : "gg-no-local-nav"}`}>
    <a className="gg-skip-link" href="#gg-main">Skip to content</a>
    <aside className="gg-global-rail" aria-label="GenuineGigs products">
      <Link className="gg-product-mark" href="/home" aria-label="GenuineGigs home"><Factory/><span>GenuineGigs</span></Link>
      <nav>{globalModules.map(({ key, label, href, icon: Icon }) => {
        const enabled = ["home","cases","work","decisions"].includes(key) || available.has(key as PlatformModuleKey);
        if (!enabled) return null;
        return <Link key={key} href={href} title={label} aria-label={label} className={module === key ? "active" : ""}><Icon/><span>{label}</span></Link>;
      })}</nav>
      <div className="gg-global-bottom"><Link href="/admin" aria-label="Administration" title="Administration"><Settings/></Link><Link href="/gigi" aria-label="Companion workspace" title="Companion workspace"><CircleHelp/></Link></div>
    </aside>

    {hasLocalNavigation && <aside className={`gg-local-nav ${mobileOpen ? "open" : ""}`} aria-label={`${shellTitle} navigation`}>
      <header><div><span>GenuineGigs</span><strong>{shellTitle}</strong></div><button onClick={() => setLocalCollapsed(value => !value)} aria-label={localCollapsed ? "Expand module navigation" : "Collapse module navigation"}>{localCollapsed ? <PanelLeftOpen/> : <PanelLeftClose/>}</button></header>
      <nav>{navigation.map((item, index) => {
        const Icon = item.icon ?? Boxes;
        const active = pathname === item.href || item.href !== `/${module}` && pathname.startsWith(`${item.href}/`);
        const previousSection = index ? navigation[index - 1].section : undefined;
        return <div key={item.href}>{item.section && item.section !== previousSection && <p>{item.section}</p>}<Link href={item.href} className={active ? "active" : ""} title={localCollapsed ? item.label : undefined}><Icon/><span>{item.label}</span>{Boolean(item.badge) && <b>{item.badge! > 99 ? "99+" : item.badge}</b>}</Link></div>;
      })}</nav>
    </aside>}

    <header className="gg-context-bar">
      <button className="gg-mobile-menu" onClick={() => setMobileOpen(value => !value)} aria-label="Open navigation"><Menu/></button>
      <div className="gg-context-identity"><span>{context.data?.workspace.name ?? "GenuineGigs workspace"}</span><i/><strong>{context.data?.plant?.name ?? "Plant unavailable"}</strong></div>
      <div className="gg-context-actions">
        <button className="gg-search-trigger" onClick={() => setSearchOpen(true)}><Search/><span>Search</span><kbd>Ctrl K</kbd></button>
        <button className="gg-refresh-button" onClick={refresh} disabled={refreshing} aria-label={refreshing ? "Refreshing workspace" : "Refresh workspace"}><RefreshCw className={refreshing ? "spin" : ""}/><span>{refreshing ? "Refreshing" : "Refresh"}</span></button>
        <div className="gg-notification-control"><button aria-label="Notifications" onClick={() => setNotificationsOpen(value => !value)}><Bell/>{Boolean(context.data?.notification_count) && <b>{context.data!.notification_count}</b>}</button>{notificationsOpen && <div className="gg-small-popover"><strong>Notifications</strong><p>{context.data?.notification_count ? `${context.data.notification_count} unread notification${context.data.notification_count === 1 ? "" : "s"}.` : "You are all caught up."}</p><Link href="/home">Open attention queue</Link></div>}</div>
        <button className={`gg-assistant-button ${companionState}`} onClick={()=>{setGigiView(undefined);setGigiOpen(true)}} aria-label={`Open Gigi companion, ${companionState}`}><i className="gg-gigi-pulse"/><Sparkles/><span>{insights.isError?"Gigi · connection unavailable":insights.isPending?"Gigi · checking":activeInsight?"Gigi needs you":openInsights.length?`Gigi watching ${openInsights.length}`:"Gigi · no new signals"}</span></button>
        <div className="gg-profile-control" ref={profileRef}><button className="gg-profile-trigger" onClick={() => setProfileOpen(value => !value)}><i>{initials}</i><span><strong>{user?.name ?? "Loading user"}</strong><small>{user?.role.replaceAll("_", " ") ?? ""}</small></span><ChevronDown/></button>{profileOpen && <div className="gg-profile-menu"><header><i>{initials}</i><div><strong>{user?.name}</strong><span>{context.data?.workspace.name} · {context.data?.plant?.name}</span></div></header><Link href="/home"><Home/>Unified home</Link><Link href="/admin"><Settings/>Administration</Link><button onClick={logout}><LogOut/>Sign out</button></div>}</div>
      </div>
    </header>

    {mobileOpen && <button className="gg-nav-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation"/>}
    <main className="gg-product-main" id="gg-main" tabIndex={-1}>{children}</main>

    {searchOpen && <div className="gg-command-layer" role="dialog" aria-modal="true" aria-label="Search and navigation"><button className="gg-command-scrim" onClick={() => setSearchOpen(false)} aria-label="Close search"/><section><header><Search/><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Search pages and modules"/><button onClick={() => setSearchOpen(false)} aria-label="Close"><X/></button></header><div>{searchable.slice(0, 12).map(item => <Link key={`${item.href}-${item.label}`} href={item.href} onClick={() => setSearchOpen(false)}><span>{item.label}</span><small>{item.href}</small></Link>)}{!searchable.length && <p>No matching pages.</p>}</div></section></div>}
    <GigiPanel open={gigiOpen} onClose={()=>setGigiOpen(false)} context={{module,route:pathname}} initialView={gigiView}/>
    {activeInsight&&!gigiOpen&&<aside className="gigi-shell-popup" role="alert"><Sparkles/><div><small>Gigi noticed · intervention required</small><strong>{activeInsight.title.replace(/^Gigi noticed:\s*/,"")}</strong><p>{activeInsight.summary}</p><footer>{activeInsight.case_id&&<Link href={`/cases/${activeInsight.case_id}`}>Open recovery case</Link>}<button onClick={()=>{void commandGigiInsight(activeInsight.id,"acknowledge").then(()=>insights.refetch())}}>Acknowledge</button><button onClick={()=>{void commandGigiInsight(activeInsight.id,"snooze").then(()=>insights.refetch())}}>Snooze 2h</button><button onClick={()=>setGigiOpen(true)}>See Gigi's work</button></footer></div></aside>}
  </div>;
}
