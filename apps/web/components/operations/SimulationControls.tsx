"use client";
import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { CirclePause,Play,RotateCcw,Siren } from "lucide-react";
import { controlV2Simulation,getV2SimulationState,injectV2Scenario } from "@/lib/api";

const labels:Record<string,string>={normal_on_plan:"Normal on-plan shift",spindle_temperature_failure:"Spindle temperature failure",dimensional_drift:"Dimensional drift and containment",supplier_material_delay:"Supplier material delay",missing_spare:"Missing repair spare",line_recovery:"Line repair and recovery",connector_outage:"Connector outage and stale data"};
export function SimulationControls(){
 const client=useQueryClient();
 const state=useQuery({queryKey:["v2-simulation"],queryFn:getV2SimulationState,refetchInterval:2000});
 const control=useMutation({mutationFn:({action,speed}:{action:"start"|"pause"|"reset"|"speed";speed?:1|10|60})=>controlV2Simulation(action,speed),onSuccess:()=>void client.invalidateQueries({queryKey:["v2-simulation"]})});
 const scenario=useMutation({mutationFn:injectV2Scenario,onSuccess:()=>void client.invalidateQueries({queryKey:["v2-simulation"]})});
 if(state.isError)return null;
 return <section className="v2-panel v2-simulation-controls"><header><div><span>Northstar source systems</span><h2>Live factory control room</h2><p>Events pass through the connector, normalization, detector and live-update path.</p></div><span className={`v2-state ${state.data?.connector.state==="fresh"?"healthy":"high"}`}>{state.data?.connector.state??"connecting"}</span></header>
  <div className="v2-sim-status"><strong>{state.data?.running?"Streaming":"Paused"}</strong><span>{state.data?.speed??1}× · sequence {state.data?.sequence??0}</span><span>{state.data?.scenario_time?new Date(state.data.scenario_time).toLocaleString():"—"}</span></div>
  <div className="v2-sim-actions"><button onClick={()=>control.mutate({action:state.data?.running?"pause":"start"})}>{state.data?.running?<CirclePause/>:<Play/>}{state.data?.running?"Pause":"Start"}</button>{([1,10,60] as const).map(speed=><button className={state.data?.speed===speed?"active":""} key={speed} onClick={()=>control.mutate({action:"speed",speed})}>{speed}×</button>)}<button onClick={()=>control.mutate({action:"reset"})}><RotateCcw/>Reset</button></div>
  <div className="v2-scenario-grid">{state.data?.available_scenarios.map(key=><button key={key} className={state.data?.scenario===key?"active":""} onClick={()=>scenario.mutate(key)}><Siren/><span>{labels[key]??key.replaceAll("_"," ")}</span></button>)}</div>
  {(control.error||scenario.error)&&<p className="v2-form-error">{(control.error??scenario.error)?.message}</p>}
  <style jsx>{`.v2-simulation-controls{margin-bottom:22px}.v2-simulation-controls header{display:flex;justify-content:space-between;gap:20px}.v2-simulation-controls header p{color:#687789}.v2-sim-status{display:flex;gap:18px;margin:18px 0;padding:14px;background:#f3f6f9;border-radius:8px}.v2-sim-status span{color:#687789}.v2-sim-actions{display:flex;gap:8px;flex-wrap:wrap}.v2-sim-actions button,.v2-scenario-grid button{display:flex;align-items:center;gap:7px;padding:10px 13px;border:1px solid #d8e0e8;border-radius:7px;background:#fff;color:#183047;font-weight:700}.v2-sim-actions button.active,.v2-scenario-grid button.active{border-color:#1765ed;background:#e9f1ff;color:#1559bd}.v2-sim-actions svg,.v2-scenario-grid svg{width:15px}.v2-scenario-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}.v2-scenario-grid button{text-align:left}@media(max-width:800px){.v2-scenario-grid{grid-template-columns:1fr 1fr}.v2-sim-status{display:grid;gap:5px}}`}</style>
 </section>;
}
