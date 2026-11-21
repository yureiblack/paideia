"use client";

// Past practice sessions on the Practice tab, newest first (decision record
// 19). Nothing records a session: the backend groups the answers, and
// answers less than 30 minutes apart are one session. Each shows when it
// was, how many answers and how many recalled, how long it took, and the
// concepts it covered.

import { Empty, QueryState } from "@/components/query-states";
import { SectionHead } from "@/components/ui";
import { usePracticeHistory } from "@/hooks/use-practice";
import { formatDateTime } from "@/lib/format";
import type { PracticeSession } from "@/lib/types";

const SHOWN_CONCEPTS = 4;

export function PracticeHistory({ environmentId }: { environmentId: string }) {
  const query = usePracticeHistory(environmentId);
  return (
    <section aria-labelledby="history-heading" className="flex min-w-0 flex-col">
      <SectionHead id="history-heading">Session history</SectionHead>
      <QueryState query={query} what="past sessions" lines={3}>
        {(sessions) =>
          sessions.length === 0 ? (
            <Empty>
              No sessions yet. Each time you practise, the session shows here: when, how
              many answers, and which concepts.
            </Empty>
          ) : (
            <>
              <ol aria-label="Past sessions">
                {sessions.map((s) => (
                  <li key={s.started_at} className="flex flex-col gap-1 border-b border-rule py-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="display text-xl leading-tight">{formatDateTime(s.started_at)}</span>
                      <span className="label text-[10px] tabular-nums">
                        {s.recalled} of {s.answers} recalled · {duration(s)}
                      </span>
                    </div>
                    <p className="text-[13px] leading-snug text-ink-2">{concepts(s)}</p>
                  </li>
                ))}
              </ol>
              <p className="label pt-2.5 text-[9px] text-ink-3">
                Answers less than 30 minutes apart count as one session. The last{" "}
                {sessions.length === 1 ? "session is" : `${sessions.length} sessions are`}{" "}
                shown.
              </p>
            </>
          )
        }
      </QueryState>
    </section>
  );
}

function duration(s: PracticeSession): string {
  const minutes = Math.round(
    (new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()) / 60000,
  );
  if (s.answers === 1) return "1 answer";
  return minutes < 1 ? `${s.answers} answers in under a minute` : `${s.answers} answers over ${minutes} min`;
}

function concepts(s: PracticeSession): string {
  const names = s.concepts.map((c) => c.name);
  if (names.length <= SHOWN_CONCEPTS) return names.join(", ");
  const rest = names.length - SHOWN_CONCEPTS;
  return `${names.slice(0, SHOWN_CONCEPTS).join(", ")} and ${rest} more`;
}
