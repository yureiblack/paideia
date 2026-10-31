"use client";

import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/config";

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
    <dl className="flex items-center gap-4 text-sm">
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
    <div className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden />
      <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="font-medium">{status}</dd>
    </div>
  );
}
