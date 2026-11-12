// Today's study plan for an environment, worked out afresh by the backend
// from the learner's state, the roadmap and the material. The time budget is
// a per-browser preference, remembered here when storage allows.

import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { endOfToday } from "@/hooks/use-practice";
import { api } from "@/lib/api";

export function usePlan(environmentId: string, minutes: number | null) {
  return useQuery({
    queryKey: ["environments", environmentId, "plan", minutes],
    queryFn: () => api.getPlan(environmentId, endOfToday(), minutes),
  });
}

const BUDGET_KEY = "paideia.plan.minutes";
const CHANGED = "paideia-plan-budget";
let remembered: string | null = null; // when storage is unavailable

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

function stored(): string | null {
  try {
    return window.localStorage.getItem(BUDGET_KEY);
  } catch {
    return remembered;
  }
}

// The server has no storage: it renders without a budget, and the browser
// takes over with the stored one.
export function useBudget(): [number | null, (minutes: number | null) => void] {
  const value = useSyncExternalStore(subscribe, stored, () => null);
  function choose(minutes: number | null) {
    remembered = minutes ? String(minutes) : null;
    try {
      if (minutes) window.localStorage.setItem(BUDGET_KEY, String(minutes));
      else window.localStorage.removeItem(BUDGET_KEY);
    } catch {
      // Storage may be unavailable; remembered keeps it for this visit.
    }
    window.dispatchEvent(new Event(CHANGED));
  }
  return [value ? Number(value) || null : null, choose];
}
