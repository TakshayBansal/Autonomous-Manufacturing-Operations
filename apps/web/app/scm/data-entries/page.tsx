import { SCMDataEntryCenter } from "@/components/scm/SCMDataEntryCenter";
import { Suspense } from "react";

export default function Page(){return <Suspense fallback={<main className="scm-state">Loading data-entry workspace…</main>}><SCMDataEntryCenter/></Suspense>}
