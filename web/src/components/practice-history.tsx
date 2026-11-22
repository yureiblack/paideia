"use client";

// Past practice sessions on the Practice tab, newest first (decision record
// 19). Nothing records a session: the backend groups the answers, and
// answers less than 30 minutes apart are one session. Each shows when it
// was, how many answers were recalled, how long it took, and the concepts
// it covered; the detail is in the sans (decision record 28).

import { Empty, QueryState } from "@/components/query-states";
import { SectionHead } from "@/components/ui";
import { usePracticeHistory } from "@/hooks/use-practice";
import { formatDateTime } from "@/lib/format";
import type { PracticeSession } from "@/lib/types";

const SHOWN_CONCEPTS = 4;

export function PracticeHistory({ environmentId }: { environmentId: string }) {
  const query = usePracticeHistory(environmentId);
  const count = query.data?.length ?? 0;
  return (
    <section aria-labelledby="history-heading" className="flex min-w-0 flex-col">
      <SectionHead id="history-heading" right={count > 0 ? `Last ${count}` : undefined}>
        Sessions
      </SectionHead>
      <QueryState query={query} what="past sessions" lines={3}>
        {(sessions) =>
          sessions.length === 0 ? (
            <Empty title="No sessions yet.">
              Each time you practise, the session shows here: when, how many answers were
              recalled, and which concepts.
            </Empty>
          ) : (
            <>
              <ol aria-label="Past sessions">
                {sessions.map((s) => (
                  <li key={s.started_at} className="flex flex-col gap-1 border-b border-rule py-3">
                    <span className="display text-xl leading-tight">{formatDateTime(s.started_at)}</span>
                    <span className="text-[13px] leading-[1.4] text-ink-2 tabular-nums">
                      {s.recalled} of {s.answers} recalled · {duration(s)}
                    </span>
                    <p className="text-[13px] leading-[1.4] text-ink-2">{concepts(s)}</p>
                  </li>
                ))}
              </ol>
              <p className="pt-2.5 text-[13px] leading-[1.4] text-ink-2">
                Answers under 30 min apart count as one session.
              </p>
            </>
          )
        }
      </QueryState>
    </section>
  );
}

// How long a session took, from its first answer to its last. A single
// answer has no length, so it says it was one answer.
function duration(s: PracticeSession): string {
  if (s.answers === 1) return "1 answer";
  const minutes = Math.round(
    (new Date(s.ended_at).getTime() - new Date(s.started_at).getTime()) / 60000,
  );
  return minutes < 1 ? "under a minute" : `${minutes} min`;
}

function concepts(s: PracticeSession): string {
  const names = s.concepts.map((c) => c.name);
  if (names.length <= SHOWN_CONCEPTS) return names.join(", ");
  const rest = names.length - SHOWN_CONCEPTS;
  return `${names.slice(0, SHOWN_CONCEPTS).join(", ")} and ${rest} more`;
}
