"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Activity, AlertTriangle, Boxes, CalendarDays, ChevronDown, CircleHelp, Database, Factory, FlaskConical, LayoutDashboard, ListChecks, LogOut, PackagePlus, PackageSearch, Plus, RefreshCw, Settings, Truck } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getSCMContext } from "@/lib/scm-api";
import { apiUrl } from "@/lib/api";
import { ProductShell, type ProductNavItem } from "@/components/platform/ProductShell";

const nav = [
  ["Control Tower", "/scm", LayoutDashboard], ["Materials", "/scm/materials", Boxes],
  ["Supply Horizon", "/scm/horizon", Activity], ["Product Readiness", "/scm/readiness", PackageSearch],
  ["Exceptions", "/scm/exceptions", AlertTriangle], ["Action Center", "/scm/actions", ListChecks],
  ["Scenario Lab", "/scm/scenarios", FlaskConical], ["Suppliers", "/scm/suppliers", Truck],
  ["Data Entries", "/scm/data-entries", PackagePlus],
  ["Imports & Quality", "/scm/imports", Database], ["Core Platform", "/platform", Boxes],
] as const;

const productNav: ProductNavItem[] = nav.map(([label, href, icon]) => ({
  label, href, icon,
  section: ["Control Tower", "Materials", "Supply Horizon", "Product Readiness"].includes(label) ? "Plan" :
    ["Exceptions", "Action Center", "Scenario Lab"].includes(label) ? "Decide" :
    ["Suppliers", "Data Entries", "Imports & Quality"].includes(label) ? "Data" : "Platform",
  badge: undefined,
}));

export function SCMFrame({ children }: { children: React.ReactNode }) {
  const query = useQuery({ queryKey: ["scm-context"], queryFn: getSCMContext, retry: false });
  if (query.isLoading) return <main className="scm-state"><Activity className="spin"/><h1>Loading planning context</h1></main>;
  if (query.error || !query.data?.plant) return <main className="scm-state error"><AlertTriangle/><h1>SCM workspace unavailable</h1><p>{query.error instanceof Error ? query.error.message : "Plant context is missing."}</p><Link href="/login">Return to sign in</Link></main>;
  return <SCMShell plant={query.data.plant}>{children}</SCMShell>;
}

function SCMShell({ plant, children }: { plant: { id: string; name: string; timezone: string; currency: string }; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const [refreshState, setRefreshState] = useState<"idle"|"refreshing"|"updated"|"error">("idle");
  const [updatedAt, setUpdatedAt] = useState(() => new Date());
  async function refreshWorkspace() {
    if (refreshState === "refreshing") return;
    setRefreshState("refreshing");
    try {
      await client.invalidateQueries({ predicate: query => String(query.queryKey[0] ?? "").startsWith("scm-") });
      router.refresh();
      setUpdatedAt(new Date());
      setRefreshState("updated");
      window.setTimeout(() => setRefreshState("idle"), 1800);
    } catch {
      setRefreshState("error");
    }
  }
  return <ProductShell module="scm" title="Supply Chain" navigation={productNav} onRefresh={refreshWorkspace} wide={pathname === "/scm/horizon"}>
    <div className="scm-shell-content"><main className="scm-main">{children}</main></div>
  </ProductShell>;
}
