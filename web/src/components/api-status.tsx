"use client";

import { useEffect, useState } from "react";

// Hardcoded for local development. This moves to an environment variable the
// moment there is a second environment to point at.
const API_BASE_URL = "http://localhost:8000";

type Status = "checking" | "ok" | "down";

async function probe(path: string): Promise<Status> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`);
    return response.ok ? "ok" : "down";
  } catch {
    return "down";
  }
}

export function ApiStatus() {
  const [api, setApi] = useState<Status>("checking");
  const [db, setDb] = useState<Status>("checking");

  useEffect(() => {
    probe("/health").then(setApi);
    probe("/health/db").then(setDb);
  }, []);

  return (
    <dl className="flex flex-col gap-3 rounded-xl border border-zinc-200 px-6 py-5 dark:border-zinc-800">
      <StatusRow label="API" status={api} />
      <StatusRow label="Database" status={db} />
    </dl>
  );
}

function StatusRow({ label, status }: { label: string; status: Status }) {
  const dot = {
    checking: "bg-zinc-400",
    ok: "bg-emerald-500",
    down: "bg-red-500",
  }[status];

  return (
    <div className="flex items-center gap-3">
      <span className={`h-2.5 w-2.5 rounded-full ${dot}`} aria-hidden />
      <dt className="w-24 text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="font-medium capitalize">{status}</dd>
    </div>
  );
}
