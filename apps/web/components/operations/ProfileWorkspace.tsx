"use client";

import Link from "next/link";
import { Building2, MapPin, Settings, ShieldCheck, UserRound } from "lucide-react";
import { V2QueryFrame } from "./V2QueryFrame";

export function ProfileWorkspace(){return <V2QueryFrame>{context=>{
  const initials=context.user.name.split(/\s+/).map(part=>part[0]).join("").slice(0,2).toUpperCase();
  return <><div className="v2-page-heading"><div><h1>Profile</h1><span>Your identity, operating role and workspace access.</span></div></div><div className="v2-profile-page"><section className="v2-profile-identity"><i>{initials}</i><div><span>Signed in as</span><h2>{context.user.name}</h2><p>{context.user.role.replaceAll("_"," ")}</p></div></section><section className="v2-panel v2-profile-facts"><div><UserRound/><span>Operational role</span><strong>{context.user.role.replaceAll("_"," ")}</strong></div><div><Building2/><span>Current plant</span><strong>{context.plant?.name??"Not assigned"}</strong></div><div><MapPin/><span>Plant timezone</span><strong>{context.plant?.timezone??"Not configured"}</strong></div><div><ShieldCheck/><span>Access scope</span><strong>Role and plant governed</strong></div></section><section className="v2-panel v2-profile-links"><div><span>Workspace settings</span><h2>Manage your operating environment</h2></div><Link href="/v2/setup"><Settings/> Operational setup</Link><Link href="/v2/integrations"><ShieldCheck/> Integration health</Link></section></div></>;
}}</V2QueryFrame>}
