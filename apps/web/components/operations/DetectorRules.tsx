"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { updateV2DetectorRule, type V2DetectorRule } from "@/lib/api";

function Rule({rule}:{rule:V2DetectorRule}){
  const client=useQueryClient();
  const [enabled,setEnabled]=useState(rule.enabled);
  const [owner,setOwner]=useState(rule.owner_role);
  const [parameters,setParameters]=useState(JSON.stringify(rule.parameters,null,2));
  const [bands,setBands]=useState(JSON.stringify(rule.severity_bands,null,2));
  const [error,setError]=useState("");
  const save=useMutation({mutationFn:()=>{try{return updateV2DetectorRule(rule,{enabled,owner_role:owner,parameters:JSON.parse(parameters) as Record<string,unknown>,severity_bands:JSON.parse(bands) as Array<Record<string,unknown>>})}catch{throw new Error("Parameters and severity bands must be valid JSON")}},onSuccess:()=>{setError("");void client.invalidateQueries({queryKey:["v2-setup"]})},onError:value=>setError(value instanceof Error?value.message:"Detector rule could not be saved")});
  return <article className="v2-detector-rule"><header><div><span>{rule.detector_key}</span><h3>{rule.name}</h3></div><label><input type="checkbox" checked={enabled} onChange={event=>setEnabled(event.target.checked)}/>{enabled?"Enabled":"Disabled"}</label></header><div className="v2-detector-sources">{rule.source_domains.map(source=><span key={source}>{source.replaceAll("_"," ")}</span>)}</div><label>Recovery owner<input value={owner} onChange={event=>setOwner(event.target.value)}/></label><div className="v2-detector-json"><label>Parameters<textarea value={parameters} onChange={event=>setParameters(event.target.value)} spellCheck={false}/></label><label>Severity bands<textarea value={bands} onChange={event=>setBands(event.target.value)} spellCheck={false}/></label></div>{error&&<p className="v2-form-error">{error}</p>}<footer><span>Approved configuration · version {rule.version}</span><button onClick={()=>save.mutate()} disabled={save.isPending}><Save/> Save governed rule</button></footer></article>;
}

export function DetectorRules({rules}:{rules:V2DetectorRule[]}){return <section className="v2-panel v2-detector-section"><div className="v2-panel-heading"><div><p>Deviation engine</p><h2>Governed detector policy</h2></div><ShieldCheck/></div><p className="v2-detector-intro">Thresholds, severity bands and recovery ownership are plant configuration. Changes are audited and affect subsequent evaluations.</p><div className="v2-detector-grid">{rules.map(rule=><Rule rule={rule} key={rule.id}/>)}</div></section>}
