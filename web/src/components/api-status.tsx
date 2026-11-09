"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/config";

type Status = "checking" | "ok" | "down";
type Probe = { status: Status; reason?: string };

// The server explains a failed check in its error detail, such as "The model
// ministral-3:8b is not downloaded.", which becomes the row's tooltip.
async function probe(path: string): Promise<Probe> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`);
    if (response.ok) return { status: "ok" };
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    return { status: "down", reason: body.detail };
  } catch {
    return { status: "down", reason: "The API is not reachable." };
  }
}

export function ApiStatus() {
  const [api, setApi] = useState<Probe>({ status: "checking" });
  const [db, setDb] = useState<Probe>({ status: "checking" });
  const [model, setModel] = useState<Probe>({ status: "checking" });

  useEffect(() => {
    probe("/health").then(setApi);
    probe("/health/db").then(setDb);
    // The language model, needed only for summaries.
    probe("/health/llm").then(setModel);
  }, []);

  return (
    <dl className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1 text-sm">
      <StatusRow label="API" {...api} />
      <StatusRow label="Database" {...db} />
      <StatusRow label="Model" {...model} />
    </dl>
  );
}

function StatusRow({ label, status, reason }: Probe & { label: string }) {
  const dot = {
    checking: "bg-zinc-400",
    ok: "bg-emerald-500",
    down: "bg-red-500",
  }[status];

  return (
    <div className="flex items-center gap-1.5" title={reason}>
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="font-medium">{status}</dd>
    </div>
  );
}
