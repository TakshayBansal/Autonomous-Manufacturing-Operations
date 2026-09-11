"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { V2Pulse } from "@/lib/api";
import { useV2Formatting } from "./V2Formatting";

export function OperatingPulse({ pulse }: { pulse: V2Pulse }) {
  const format=useV2Formatting();
  const data = [
    { point: "Shift start", plan: 0, actual: 0, forecast: null },
    { point: "Now", plan: pulse.expected_now, actual: pulse.actual, forecast: pulse.actual },
    { point: "Shift end", plan: pulse.target, actual: null, forecast: pulse.forecast },
  ];
  const gap = pulse.forecast - pulse.target;
  return <section className="v2-panel v2-operating-pulse">
    <div className="v2-panel-heading"><div><p>Today&apos;s production trajectory</p><h2>{gap < 0 ? `${format.number(Math.abs(gap))} units at risk` : "On track to hit plan"}</h2></div><span className={gap < 0 ? "v2-state high" : "v2-state healthy"}>{gap < 0 ? "At risk" : "On plan"}</span></div>
    <div className="v2-chart" role="img" aria-label="Production plan, actual and forecast trajectory">
      <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 14, right: 16, bottom: 4, left: 0 }}>
        <XAxis dataKey="point" axisLine={false} tickLine={false}/><YAxis axisLine={false} tickLine={false} width={48}/><Tooltip/>
        <Line type="monotone" dataKey="plan" stroke="#7a8793" strokeWidth={2} dot={false}/>
        <Line type="monotone" dataKey="actual" stroke="#2563eb" strokeWidth={3} connectNulls={false}/>
        <Line type="monotone" dataKey="forecast" stroke="#d97706" strokeWidth={3} strokeDasharray="7 6" connectNulls={false}/>
      </LineChart></ResponsiveContainer>
    </div>
    <dl className="v2-pulse-metrics"><div><dt>Target</dt><dd>{format.number(pulse.target)}</dd></div><div><dt>Actual now</dt><dd>{format.number(pulse.actual)}</dd></div><div><dt>Forecast end</dt><dd>{format.number(pulse.forecast)}</dd></div></dl>
  </section>;
}
