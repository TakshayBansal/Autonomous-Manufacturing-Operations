import { Suspense } from "react";
import { V2AuthGateway } from "@/components/operations/V2AuthGateway";

export default function LoginPage() {
  return <Suspense fallback={<main className="v2-auth-shell"/>}><V2AuthGateway /></Suspense>;
}
