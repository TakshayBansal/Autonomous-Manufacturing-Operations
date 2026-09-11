"use client";

import { useEffect, useState } from "react";

export function useRouteSelection(parameter: string) {
  const [value, setValue] = useState("");

  useEffect(() => {
    setValue(new URLSearchParams(window.location.search).get(parameter) ?? "");
  }, [parameter]);

  function select(nextValue: string) {
    setValue(nextValue);
    const url = new URL(window.location.href);
    if (nextValue) url.searchParams.set(parameter, nextValue);
    else url.searchParams.delete(parameter);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    window.dispatchEvent(new CustomEvent("genuinegigs:selection", { detail: { parameter, value: nextValue } }));
  }

  return [value, select] as const;
}
