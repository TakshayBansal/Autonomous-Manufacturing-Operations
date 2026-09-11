"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2Context, type V2Context } from "@/lib/api";
import { V2AppShell } from "./V2AppShell";

export function V2QueryFrame({ children }: { children: (context: V2Context, shiftId?: string) => React.ReactNode }) {
  const query = useQuery({ queryKey: ["v2-context"], queryFn: getV2Context });
  if (query.isLoading) return <div className="v2-loading">Loading plant context…</div>;
  if (query.error || !query.data?.plant) return <div className="v2-error"><AlertTriangle/><h1>Plant context is unavailable</h1><Link href="/login">Return to sign in</Link></div>;
  const shift = query.data.shifts.find((item) => item.status === "active") ?? query.data.shifts[0];
  return <V2AppShell context={query.data}>{children(query.data, shift?.id)}</V2AppShell>;
}
