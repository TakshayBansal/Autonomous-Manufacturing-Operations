"use client";
import {useEffect} from "react";

export default function AppError({error,reset}:{error:Error&{digest?:string};reset:()=>void}){
 useEffect(()=>{
  const transient=/chunk|dynamically imported|failed to fetch|networkerror|load failed/i.test(error.message);
  const key=`gg-route-recovery:${window.location.pathname}`;
  if(transient&&!sessionStorage.getItem(key)){sessionStorage.setItem(key,"1");window.location.reload();return}
  sessionStorage.removeItem(key);
 },[error]);
 return <main className="gg-route-error"><p>GENUINEGIGS / ROUTE RECOVERY</p><h1>This workspace view did not load cleanly.</h1><span>{error.message||"The browser and running deployment may be temporarily out of sync."}</span><div><button onClick={reset}>Try again</button><button onClick={()=>window.location.reload()}>Reload current view</button><a href="/home">Return to command center</a></div></main>;
}
