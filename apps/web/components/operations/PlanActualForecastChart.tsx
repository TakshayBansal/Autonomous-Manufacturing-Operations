"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMemo } from "react";
import { useV2Formatting } from "./V2Formatting";

type Point = { at: string; plan?: number; actual?: number; forecast?: number };

export function PlanActualForecastChart({ points, now }: { points: Point[]; now?: string }) {
  const format = useV2Formatting();
  const data = useMemo(() => points.map(point => ({ ...point, timestamp: new Date(point.at).getTime() })), [points]);
  return <div className="v2-trajectory-chart" role="img" aria-label="Production plan, actual output and end-of-shift forecast">
    <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 14, right: 18, bottom: 2, left: 0 }}>
      <CartesianGrid vertical={false} stroke="#e8edf1"/>
      <XAxis dataKey="timestamp" type="number" domain={["dataMin", "dataMax"]} tickFormatter={value => format.time(new Date(value).toISOString())} axisLine={false} tickLine={false}/>
      <YAxis width={48} axisLine={false} tickLine={false}/>
      <Tooltip labelFormatter={value => format.time(new Date(Number(value)).toISOString())} formatter={(value, name) => [format.number(Number(value)), String(name)]}/>
      {now && <ReferenceLine x={new Date(now).getTime()} stroke="#c7d0d8" strokeDasharray="3 4" label={{value:"Now",position:"insideTopRight",fill:"#7a8793",fontSize:10}}/>}
      <Line isAnimationActive={false} type="monotone" dataKey="plan" name="Plan" stroke="#7a8793" strokeWidth={2} dot={false} connectNulls/>
      <Line isAnimationActive={false} type="monotone" dataKey="actual" name="Actual" stroke="#2563eb" strokeWidth={3} dot={false} activeDot={{r:4}} connectNulls/>
      <Line isAnimationActive={false} type="monotone" dataKey="forecast" name="Forecast" stroke="#d97706" strokeWidth={3} strokeDasharray="7 6" dot={{r:3,fill:"#fff"}} connectNulls/>
    </LineChart></ResponsiveContainer>
  </div>;
}
