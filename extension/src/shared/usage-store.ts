/**
 * One shared copy of the server's usage numbers (GET /usage), so the corner
 * meter in App.tsx and the capture/limit logic in AskTab.tsx always agree
 * without passing props through the shell. A refresh never consumes quota
 * (the endpoint is read-only); callers refresh on open, after each capture
 * or chat answer, and after signing in or out (the counted key changes).
 */

import { useSyncExternalStore } from "react";

import type { UsageResponse } from "@shared/types";

import { getUsage } from "./api-client";

let current: UsageResponse | null = null;
const listeners = new Set<() => void>();

function publish(next: UsageResponse): void {
  current = next;
  listeners.forEach((listener) => listener());
}

export async function refreshUsage(): Promise<void> {
  try {
    publish(await getUsage());
  } catch {
    // Offline or the server is waking: keep showing the last known numbers.
    // The meter is a convenience; a failed refresh must never surface as an error.
  }
}

export function useUsage(): UsageResponse | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current
  );
}

export type ActiveLimit =
  | { kind: "daily"; used: number; limit: number; resetsAt: Date }
  | { kind: "monthly"; used: number; limit: number; resetsAt: Date }
  | { kind: "global"; resetsAt: Date };

/**
 * Which limit currently blocks capturing, if any. Mirrors the server's
 * order: the person's own monthly allowance, then their daily one, then the
 * global capacity cap. Admins are never blocked.
 */
export function activeCaptureLimit(usage: UsageResponse | null): ActiveLimit | null {
  if (!usage || usage.unlimited) return null;
  const { captures_today: day, captures_month: month } = usage;
  if (month.used >= month.limit) {
    return { kind: "monthly", used: month.used, limit: month.limit, resetsAt: new Date(month.resets_at) };
  }
  if (day.used >= day.limit) {
    return { kind: "daily", used: day.used, limit: day.limit, resetsAt: new Date(day.resets_at) };
  }
  if (usage.global_blocked) {
    return { kind: "global", resetsAt: new Date(day.resets_at) };
  }
  return null;
}
