"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Database, Factory, RadioTower, ShieldCheck } from "lucide-react";
import { getV2Edge, getV2ForecastEvaluation, getV2Integrations, getV2Setup } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";

function AdminContent(){
  const setup=useQuery({queryKey:["v2-setup"],queryFn:getV2Setup});
  const integrations=useQuery({queryKey:["v2-integrations"],queryFn:getV2Integrations});
  const edge=useQuery({queryKey:["v2-edge"],queryFn:getV2Edge});
  const evaluation=useQuery({queryKey:["v2-forecast-evaluation"],queryFn:getV2ForecastEvaluation});
  const configured=setup.data?.completed_stages.length??0;
  const unhealthy=integrations.data?.filter(item=>item.health.state!=="healthy").length??0;
  const heading=<div className="v2-page-heading"><div><p>Administration</p><h1>Keep the operating model trustworthy.</h1><span>Plant structure, source ownership, edge health and activation controls in one governed workspace.</span></div></div>;
  if(setup.isLoading||integrations.isLoading||edge.isLoading||evaluation.isLoading)return <>{heading}<div className="v2-loading-region">Loading governed administration evidence…</div></>;
  const loadError=setup.error||integrations.error||edge.error||evaluation.error;
  return <>{heading}
    {loadError&&<div className="v2-degraded"><AlertTriangle/><div><strong>Some administration evidence could not be loaded.</strong><p>Unavailable infrastructure evidence is not represented as healthy or zero.</p></div><button onClick={()=>{void setup.refetch();void integrations.refetch();void edge.refetch();void evaluation.refetch()}}>Retry</button></div>}
    <div className="v2-admin-grid"><Link href="/v2/setup"><Factory/><div><span>Plant model</span><h2>Operational setup</h2><p>{configured} activation stages completed · {setup.data?.hierarchy.areas??0} areas · {setup.data?.hierarchy.lines??0} lines</p></div><ArrowRight/></Link><Link href="/v2/integrations"><Database/><div><span>IT sources</span><h2>Integrations and mappings</h2><p>{integrations.data?.length??0} connections · {unhealthy} requiring attention · writes remain policy controlled</p></div><ArrowRight/></Link><Link href="/v2/setup#edge"><RadioTower/><div><span>OT boundary</span><h2>Plant edge</h2><p>{edge.data?.gateways.length??0} gateways · outbound-only transport and signed configuration</p></div><ArrowRight/></Link><Link href="/audit"><ShieldCheck/><div><span>Governance</span><h2>Audit and authority</h2><p>Review configuration, agent, approval and external-action evidence.</p></div><ArrowRight/></Link></div>
    <section className="v2-model-assurance"><header><div><span>Model assurance</span><h2>Forecast versus simple baseline</h2></div><span className={`v2-state ${evaluation.data?.status==="candidate_better"?"healthy":"watch"}`}>{evaluation.error?"unavailable":evaluation.data?.status.replaceAll("_"," ")??"evaluating"}</span></header><div><article><span>Rolling samples</span><strong>{evaluation.data?.sample_size??"—"}</strong></article><article><span>Candidate MAE</span><strong>{evaluation.data?.metrics.mae??"—"}</strong></article><article><span>Baseline MAE</span><strong>{evaluation.data?.metrics.baseline_mae??"—"}</strong></article><article><span>Improvement</span><strong>{evaluation.data?.metrics.improvement_over_baseline==null?"—":`${(evaluation.data.metrics.improvement_over_baseline*100).toFixed(1)}%`}</strong></article></div>{evaluation.data?.limitations.map(item=><p key={item}><AlertTriangle/>{item}</p>)}</section>
    <section className="v2-admin-principles"><h2>Deployment invariants</h2><div><article><strong>Systems of record remain authoritative</strong><p>Mappings define ownership. GenuineGigs does not silently create a parallel operational master.</p></article><article><strong>Read-only until explicitly enabled</strong><p>Connector capability, policy, user authority and deployment switches must all allow a write.</p></article><article><strong>Stale data is visibly stale</strong><p>Source age and failures degrade dependent decisions instead of being presented as live truth.</p></article></div></section></>;
}
export function V2Admin(){return <V2QueryFrame>{context=>context.user.role==="admin"?<AdminContent/>:<div className="v2-degraded"><ShieldCheck/><strong>Administrator authority is required.</strong></div>}</V2QueryFrame>}
