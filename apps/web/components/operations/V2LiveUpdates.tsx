"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiUrl } from "@/lib/api";

const EVENT_QUERIES: Record<string, string[]> = {
  "production.actual.updated": ["command-center", "v2-kpis", "operations-overview", "line-workspace", "v2-role-home"],
  "downtime.updated": ["command-center", "v2-kpis", "operations-overview", "line-workspace", "maintenance-workspace", "v2-role-home"],
  "quality.event.updated": ["command-center", "v2-kpis", "line-workspace", "quality-workspace", "v2-role-home"],
  "inventory.position.updated": ["command-center", "line-workspace", "material-readiness", "maintenance-workspace", "v2-role-home"],
  "supplier.commitment.updated": ["command-center", "material-readiness", "procurement-v2", "v2-role-home"],
  "material.readiness.updated": ["command-center", "line-workspace", "material-readiness", "procurement-v2", "v2-role-home"],
  "machine.event.updated": ["command-center", "line-workspace", "maintenance-workspace", "maintenance-asset", "v2-role-home"],
  "machine.signal.updated": ["line-workspace", "maintenance-workspace", "maintenance-asset"],
  "maintenance.work.updated": ["line-workspace", "maintenance-workspace", "maintenance-asset", "my-work", "v2-role-home"],
  "connector.health.changed": ["v2-integrations", "v2-role-home"],
  "action.created": ["command-center", "line-workspace", "deviation", "my-work", "v2-notifications", "v2-role-home"],
  "action.updated": ["command-center", "line-workspace", "deviation", "my-work", "v2-notifications", "v2-role-home"],
  "gigi.activity.created": ["command-center", "gigi-briefing", "v2-notifications"],
};

export function V2LiveUpdates({ plantId }: { plantId: string }) {
  const client = useQueryClient();
  useEffect(() => {
    const source = new EventSource(apiUrl(`/api/v2/stream?plant_id=${encodeURIComponent(plantId)}`), { withCredentials: true });
    const pending = new Set<string>();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => {
      timer = undefined;
      for (const key of pending) {
        void client.invalidateQueries({ queryKey: [key], refetchType: "active" });
      }
      pending.clear();
    };
    const schedule = (keys: string[]) => {
      keys.forEach(key => pending.add(key));
      if (!timer) timer = setTimeout(flush, 350);
    };
    const listeners = new Map<string, EventListener>();
    const recoveryKeys = ["command-center", "line-workspace", "deviation", "recovery", "my-work", "v2-notifications", "v2-role-home"];
    const deviationKeys = ["command-center", "v2-kpis", "operations-overview", "line-workspace", "deviation", "my-work", "v2-notifications", "v2-role-home"];
    const names = [
      "deviation.created", "deviation.updated", "deviation.resolved", "action.created", "action.updated",
      "production.actual.updated", "downtime.updated", "quality.event.updated", "inventory.position.updated",
      "supplier.commitment.updated", "machine.event.updated", "machine.signal.updated", "maintenance.work.updated",
      "material.readiness.updated", "connector.health.changed", "gigi.activity.created", "recovery.case.opened",
      "recovery.options.generated", "recovery.strategy.recommended", "recovery.strategy.selected",
      "recovery.execution.started", "recovery.monitoring.started", "recovery.outcome.detected", "recovery.verified",
      "recovery.failed", "recovery.learning.updated",
    ];
    names.forEach(name => {
      const keys = name.startsWith("recovery.") ? recoveryKeys : name.startsWith("deviation.") ? deviationKeys : EVENT_QUERIES[name] ?? [];
      const listener = (() => schedule(keys)) as EventListener;
      listeners.set(name, listener);
      source.addEventListener(name, listener);
    });
    return () => {
      source.close();
      if (timer) clearTimeout(timer);
      listeners.forEach((listener, name) => source.removeEventListener(name, listener));
    };
  }, [client, plantId]);
  return null;
}
