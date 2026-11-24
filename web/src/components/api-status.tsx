"use client";

// The health of everything Paideia needs, in the masthead: one line saying
// all is well or naming the first problem, which opens the four checks
// with the server's own reasons.

import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/config";

import { Mark, POPOVER_WIDTH, useDismiss, useInsideWindow } from "./ui";

type Status = "checking" | "ok" | "down";
type Probe = { status: Status; reason?: string };

// The server explains a failed check in its error detail, such as "The model
// ministral-3:8b is not downloaded.", which the open panel shows.
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
  const [worker, setWorker] = useState<Probe>({ status: "checking" });
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDListElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(panel, open, close, trigger);
  useInsideWindow(list, open);

  useEffect(() => {
    probe("/health").then(setApi);
    probe("/health/db").then(setDb);
    // The language model, needed for everything it writes.
    probe("/health/llm").then(setModel);
    // The background worker, which reads documents and runs the model's
    // work. Checked again every half minute: it is started separately.
    const check = () => probe("/health/worker").then(setWorker);
    check();
    const timer = window.setInterval(check, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const rows: [string, Probe][] = [
    ["API", api],
    ["Database", db],
    ["Model", model],
    ["Worker", worker],
  ];
  const down = rows.find(([, p]) => p.status === "down");
  const checking = rows.some(([, p]) => p.status === "checking");
  const summary = down ? `${down[0]} down` : checking ? "Checking…" : "All systems ok";

  return (
    <div ref={panel} className="relative">
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={`System status: ${summary}`}
        className={`label flex items-center gap-2 ${down ? "text-ink" : "text-ink-3"} hover:text-ink`}
      >
        {down ? <Mark /> : <span aria-hidden>■</span>}
        <span className="hidden tab:inline">{summary}</span>
      </button>
      {open && (
        <dl ref={list} className={`absolute right-0 top-full z-30 mt-3 w-72 ${POPOVER_WIDTH} border border-ink bg-paper`}>
          {rows.map(([label, { status, reason }]) => (
            <div
              key={label}
              className="grid grid-cols-[1fr_auto] gap-x-2.5 gap-y-1 border-b border-rule px-3.5 py-2.5 last:border-b-0"
            >
              <dt className="label flex items-center gap-2.5">
                {status === "down" ? <Mark /> : <span aria-hidden>●</span>}
                {label}
              </dt>
              <dd className={`label ${status === "down" ? "text-ink" : "text-ink-2"}`}>{status}</dd>
              {reason && <dd className="col-span-2 text-[13px] leading-snug text-ink-2">{reason}</dd>}
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
