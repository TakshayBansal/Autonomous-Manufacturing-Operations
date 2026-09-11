"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Bot, CheckCircle2, Clock3 } from "lucide-react";
import { commandV2Action, getV2MyWork, type V2Action } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";
import { DegradedDataBanner, openContextualGigi, PlantActivationState, SeverityBadge } from "./OperationalPrimitives";

function ActionCard({ item }: { item: V2Action }) {
  const format=useV2Formatting();
  const client = useQueryClient();
  const command: "start" | "complete" = item.status === "waiting" || item.status === "open" || item.status === "accepted" ? "start" : "complete";
  const mutation = useMutation({ mutationFn: () => commandV2Action(item.id, command, { summary: "Recovery completed with operational evidence." }), onSuccess: () => client.invalidateQueries({ queryKey: ["my-work"] }) });
  return <article className="v2-action-card"><div><SeverityBadge severity={item.priority}/><h3>{item.title}</h3><p><strong>Why:</strong> {item.expected_outcome.recovery_case_id?"This is a governed step in the selected recovery strategy.":"Linked operational recovery is waiting on this outcome."}</p>{item.expected_outcome.expected_recovered_units!=null&&<p><strong>Expected effect:</strong> protect up to {format.number(Number(item.expected_outcome.expected_recovered_units))} units</p>}<p><Clock3/> {item.due_at ? format.time(item.due_at) : "No deadline"} · {item.owner_role?.replaceAll("_", " ")}</p>{item.blocked_by?.map(blocker=><div className="v2-action-blocker" key={blocker.title}><strong>Not an employee miss</strong><span>Waiting on {blocker.owner_role?.replaceAll("_"," ")??"upstream dependency"}</span><p>{blocker.title} · {blocker.elapsed_minutes} min dependency delay</p></div>)}</div><div className="v2-action-buttons"><button onClick={() => mutation.mutate()} disabled={mutation.isPending}>{command === "start" ? item.status === "waiting" ? "Resume task" : "Start task" : "Complete"}<ArrowRight/></button><button className="secondary" onClick={()=>openContextualGigi(`My Work · ${item.title}`,`Explain why this action matters, its evidence, dependencies, and safest next step: ${item.title}`)}><Bot/> Ask Gigi</button></div>{mutation.error&&<p className="v2-form-error" role="alert">{mutation.error instanceof Error?mutation.error.message:"The action could not be updated."}</p>}</article>;
}
function MyWorkContent() {
  const query = useQuery({ queryKey: ["my-work"], queryFn: getV2MyWork });
  const groups = [["NOW", query.data?.now], ["NEXT", query.data?.next], ["WAITING", query.data?.waiting], ["DONE TODAY", query.data?.done_today]] as const;
  const total = groups.reduce((sum, [, items]) => sum + (items?.length ?? 0), 0);
  return <><div className="v2-page-heading"><div><h1>My Work</h1><span>Your ordered operational plan · consequence first.</span></div></div>{query.isLoading ? <div className="v2-loading-region">Loading your work…</div> : query.error ? <DegradedDataBanner title="Your operational work could not be loaded." detail="Do not infer that there is no assigned work. Restore the data path or retry." onRetry={() => query.refetch()}/> : total === 0 ? <PlantActivationState compact/> : <div className="v2-work-groups">{groups.map(([label, items]) => <section key={label}><header><h2>{label}</h2><span>{items?.length ?? 0}</span></header>{items?.length ? items.map(item => <ActionCard item={item} key={item.id}/>) : <div className="v2-empty-work"><CheckCircle2/><span>Clear</span></div>}</section>)}</div>}</>;
}
export function MyWork() { return <V2QueryFrame>{() => <MyWorkContent/>}</V2QueryFrame>; }
