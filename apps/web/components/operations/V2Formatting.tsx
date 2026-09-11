"use client";
import { createContext, useContext } from "react";

export type V2FormatSettings = { locale:string; timezone:string; currency:string };
const fallback:V2FormatSettings={locale:"en-US",timezone:"UTC",currency:"USD"};
const Context=createContext<V2FormatSettings>(fallback);

export function V2FormattingProvider({settings,children}:{settings:V2FormatSettings;children:React.ReactNode}) {
  return <Context.Provider value={settings}>{children}</Context.Provider>;
}

export function useV2Formatting(){
  const settings=useContext(Context);
  return {
    ...settings,
    number:(value:number,options?:Intl.NumberFormatOptions)=>new Intl.NumberFormat(settings.locale,options).format(value),
    money:(value:number,currency=settings.currency)=>new Intl.NumberFormat(settings.locale,{style:"currency",currency,maximumFractionDigits:0}).format(value),
    percent:(value:number)=>new Intl.NumberFormat(settings.locale,{style:"percent",maximumFractionDigits:1}).format(value),
    date:(value:string|Date,options?:Intl.DateTimeFormatOptions)=>new Intl.DateTimeFormat(settings.locale,{timeZone:settings.timezone,...options}).format(new Date(value)),
    time:(value:string|Date)=>new Intl.DateTimeFormat(settings.locale,{timeZone:settings.timezone,hour:"2-digit",minute:"2-digit"}).format(new Date(value)),
    dateTime:(value:string|Date)=>new Intl.DateTimeFormat(settings.locale,{timeZone:settings.timezone,dateStyle:"medium",timeStyle:"short"}).format(new Date(value)),
  };
}
