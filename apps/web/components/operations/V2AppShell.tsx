"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Activity, Bell, Bot, CalendarDays, ChevronDown, Factory, Gauge, Library, LogOut, Menu, PackageSearch, Settings, ShieldCheck, Sparkles, UserRound, UserRoundCheck, Wrench } from "lucide-react";
import { getV2Integrations, mutate, type V2Context } from "@/lib/api";
import { V2LiveUpdates } from "./V2LiveUpdates";
import { V2FormattingProvider } from "./V2Formatting";
import { OperationalCommandLayer } from "./OperationalCommandLayer";
import { ProductShell, type ProductNavItem } from "@/components/platform/ProductShell";

const nav = [
  ["Overview", "/operations", Gauge], ["My Work", "/operations/my-work", UserRoundCheck],
  ["Production", "/operations/production", Activity], ["Materials", "/operations/materials", PackageSearch],
  ["Quality", "/operations/quality", ShieldCheck], ["Maintenance", "/operations/maintenance", Wrench],
  ["Improvement", "/operations/improvement", Sparkles], ["Knowledge", "/operations/knowledge", Library],
  ["Briefing", "/operations/briefing", Library],
] as const;
const adminNav = [["Admin", "/operations/admin", Settings], ["Integrations", "/operations/integrations", ShieldCheck], ["Setup", "/operations/setup", Factory], ["Corporate", "/operations/corporate", Gauge]] as const;
const corporateNav = [["Corporate", "/operations/corporate", Gauge]] as const;

const roleRoutes:Record<string,Set<string>>={
  quality_inspector:new Set(["Overview","My Work","Production","Quality","Improvement","Knowledge","Briefing"]),
  quality_manager:new Set(["Overview","My Work","Production","Quality","Improvement","Knowledge","Briefing"]),
  maintenance_technician:new Set(["Overview","My Work","Production","Maintenance","Improvement","Knowledge","Briefing"]),
  maintenance_manager:new Set(["Overview","My Work","Production","Maintenance","Improvement","Knowledge","Briefing"]),
  purchase_executive:new Set(["Overview","My Work","Materials","Knowledge","Briefing"]),
  purchase_manager:new Set(["Overview","My Work","Materials","Improvement","Knowledge","Briefing"]),
  store_manager:new Set(["Overview","My Work","Materials","Quality","Briefing"]),
  gate_operator:new Set(["Overview","My Work","Materials"]),
};

export function V2AppShell({ context, children }: { context: V2Context; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const integrations=useQuery({queryKey:["v2-integrations"],queryFn:getV2Integrations,refetchInterval:30_000});
  const shift = context.shifts.find((item) => item.status === "active") ?? context.shifts[0];
  const allowed=roleRoutes[context.user.role];
  const primaryNav=allowed?nav.filter(([label])=>allowed.has(label)):nav;
  const sourceStates=integrations.data?.map(row=>row.health.state)??[];
  const sourceState=sourceStates.some(state=>["error","stale"].includes(state))?"degraded":sourceStates.length&&sourceStates.every(state=>state==="healthy")?"live":"unknown";
  const defaultGigiContext=`${context.plant?.name??"Plant unavailable"} · ${shift?.name??"No active shift"}`;
  const now = new Date();
  const initials = context.user.name.split(/\s+/).map(part=>part[0]).join("").slice(0,2).toUpperCase();
  const allNav = [...primaryNav, ...(context.user.role === "admin" ? adminNav : context.user.role === "plant_manager" ? corporateNav : [])];
  const productNav: ProductNavItem[] = allNav.map(([label, href, icon]) => ({ label, href, icon, section: ["Overview", "My Work", "Production"].includes(label) ? "Operate" : ["Materials", "Quality", "Maintenance"].includes(label) ? "Functions" : "Improve" }));
  return <V2FormattingProvider settings={{locale:context.plant?.locale??"en-US",timezone:context.plant?.timezone??"UTC",currency:context.plant?.currency??"USD"}}>
    {context.plant && <V2LiveUpdates plantId={context.plant.id}/>} 
    <ProductShell module="operations" navigation={productNav}>
      <main className="v2-main" id="v2-main" tabIndex={-1}>{children}</main>
    </ProductShell>
  </V2FormattingProvider>;
}
