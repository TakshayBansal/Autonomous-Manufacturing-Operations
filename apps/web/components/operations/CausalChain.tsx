"use client";

import { ArrowRight, CircleDot, GitBranch, ShieldQuestion } from "lucide-react";
import type { V2CausalContext } from "@/lib/api";

export function CausalChain({ context }: { context: V2CausalContext }) {
  return <div className="v2-causal-chain" aria-label="Operational causal-action chain">
    {context.chain.map((node,index)=><div className={`v2-causal-node ${node.type}`} key={`${node.type}-${node.id??index}`}><span>{node.type === "signal" ? <CircleDot/> : node.type === "action" ? <GitBranch/> : <ShieldQuestion/>}</span><div><small>{node.type}</small><strong>{node.label}</strong><i>{node.state.replaceAll("_"," ")}</i></div>{index<context.chain.length-1&&<ArrowRight className="connector"/>}</div>)}
  </div>;
}

export function DependencyGraph({ context }: { context: V2CausalContext }) {
  return <div className="v2-dependency-graph">{context.dependencies.length?context.dependencies.map(item=><article key={item.id}><i className={item.status}/><div><span>{item.type.replaceAll("_"," ")}</span><strong>{item.title}</strong><small>{item.owner_role?.replaceAll("_"," ")??"Owner required"} · {item.status.replaceAll("_"," ")}</small></div></article>):<p>No blocking dependency is recorded for the current recovery action.</p>}</div>;
}
