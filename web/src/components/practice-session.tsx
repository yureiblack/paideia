"use client";

// One practice session, one item at a time. Answer first, from memory: a
// choice, true or false, or, for a short answer or flashcard, your own answer
// before revealing the stored one and marking whether you knew it. Then the
// right answer, why, the passages it comes from, and when the item comes
// back. Nothing here is a score: it only decides when items return. The
// question is set in the display face, no larger than 38 px; everything
// said about it is in the sans (decision record 28).

import { useEffect, useRef, useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { MathsText } from "@/components/maths-text";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, Mark } from "@/components/ui";
import { ExerciseForm } from "@/components/exercise-form";
import { useAnswer, usePracticeSession } from "@/hooks/use-practice";
import { formatDateTime } from "@/lib/format";
import type { AttemptInput, AttemptResult, PracticeItem, PracticeKind } from "@/lib/types";

const KIND_LABEL: Record<PracticeKind, string> = {
  short_answer: "Short answer",
  multiple_choice: "Multiple choice",
  true_false: "True or false",
  flashcard: "Flashcard",
  exercise: "Exercise",
};

export function PracticeSession({
  environmentId,
  conceptIds,
  started,
  title,
  onDone,
}: {
  environmentId: string;
  conceptIds: string[] | null;
  started: number;
  title: string;
  onDone: () => void;
}) {
  const query = usePracticeSession(environmentId, conceptIds, started);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<AttemptResult[]>([]);

  if (query.isPending) return <Loading what="the practice items" lines={4} />;
  if (query.isError) {
    return (
      <div className="flex flex-col items-start gap-4">
        <LoadError
          what="the practice items"
          error={query.error}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
        <button type="button" onClick={onDone} className={button.link}>
          Back to practice
        </button>
      </div>
    );
  }
  const items = query.data;
  const back = (
    <button type="button" onClick={onDone} className={`${button.outline} w-fit`}>
      <span aria-hidden>← </span>Back to practice
    </button>
  );
  if (items.length === 0) {
    return (
      <Empty title="Nothing to practise here right now." action={back}>
        None of these concepts has a question waiting. Questions come back on their own
        days, or once their stage is prepared.
      </Empty>
    );
  }
  if (index >= items.length) {
    const tomorrow = results.filter((r) => r.gap_days <= 1).length;
    return (
      <section aria-labelledby="done-heading" className="flex max-w-[640px] flex-col items-start gap-4">
        <p className="label">
          {items.length} / {items.length} — done
        </p>
        <h2 id="done-heading" className="display text-[44px] leading-[0.95] tracking-[-0.03em] tab:text-[56px]">
          Session done.
        </h2>
        <p className="text-[16px] leading-[1.55] text-ink-2">
          You practised {items.length} {items.length === 1 ? "item" : "items"}.{" "}
          {tomorrow === results.length
            ? "Their concepts all come back tomorrow; each time you recall one, it comes back further apart."
            : tomorrow > 0
              ? `${tomorrow} of your answers bring their concept back tomorrow; the rest come back later, further apart each time you recall them.`
              : "Their concepts come back later, further apart each time you recall them."}
        </p>
        {back}
      </section>
    );
  }
  const item = items[index];
  return (
    <section aria-labelledby="session-heading" className="flex flex-col gap-6">
      <div className="flex items-center gap-4 border-b border-ink pb-3">
        <h2 id="session-heading" className="label min-w-0 flex-1 truncate">
          {title}
        </h2>
        <span aria-hidden className="label hidden tracking-[0.12em] tab:block">
          {"■".repeat(index + 1)}
          {"□".repeat(items.length - index - 1)}
        </span>
        <span className="label shrink-0 font-semibold">
          {index + 1} of {items.length}
        </span>
      </div>
      <ItemCard
        key={item.id}
        environmentId={environmentId}
        item={item}
        number={index + 1}
        onAnswered={(result) => setResults([...results, result])}
        onNext={() => setIndex(index + 1)}
        last={index === items.length - 1}
      />
      <div className="border-t border-ink pt-4">
        <button type="button" onClick={onDone} className={button.link}>
          Stop here
        </button>
      </div>
    </section>
  );
}

const LETTERS = "ABCDEFGH";

function ItemCard({
  environmentId,
  item,
  number,
  onAnswered,
  onNext,
  last,
}: {
  environmentId: string;
  item: PracticeItem;
  number: number;
  onAnswered: (result: AttemptResult) => void;
  onNext: () => void;
  last: boolean;
}) {
  const answer = useAnswer(environmentId);
  const shownAt = useRef(0);
  const [choice, setChoice] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [revealed, setRevealed] = useState(false);
  const result = answer.data;

  useEffect(() => {
    shownAt.current = performance.now();
  }, []);

  function submit(input: AttemptInput) {
    const seconds = Math.round((performance.now() - shownAt.current) / 100) / 10;
    answer.mutate(
      { itemId: item.id, input: { ...input, seconds } },
      { onSuccess: onAnswered },
    );
  }

  const selfMarked = item.kind === "short_answer" || item.kind === "flashcard";
  return (
    <article className="grid gap-8 desk:grid-cols-[minmax(0,1fr)_300px] desk:gap-12">
      <div className="flex min-w-0 flex-col gap-6">
        <p className="label text-ink-2">
          {KIND_LABEL[item.kind]} · {item.concept.name}
        </p>
        <p
          className={
            item.kind === "exercise"
              ? "max-w-[640px] text-[18px] leading-[1.7]"
              : "display max-w-[720px] text-[28px] leading-[1.08] tracking-[-0.02em] text-balance tab:text-[34px] desk:text-[38px]"
          }
        >
          <span className="sr-only">Question {number}: </span>
          <MathsText text={item.prompt} />
        </p>

        {item.kind === "exercise" && item.exercise && (
          <ExerciseForm
            form={item.exercise.form}
            pending={answer.isPending}
            right={result?.right ?? null}
            onSubmit={(cells, choice) =>
              submit({ cells, choice, variant: item.exercise?.variant })
            }
          />
        )}

        {result?.steps && (
          <section aria-label="Worked solution" className="flex flex-col gap-3 border-t border-rule pt-4">
            <h3 className="label text-ink-2">Worked solution</h3>
            <ol className="flex max-w-[640px] flex-col gap-2 text-[17px] leading-[1.6]">
              {result.steps.map((step, n) => (
                <li key={n} className="overflow-x-auto">
                  <MathsText text={step} />
                </li>
              ))}
            </ol>
          </section>
        )}

        {item.kind === "multiple_choice" && item.options && (
          <fieldset disabled={!!result} className="flex flex-col border-t border-ink">
            <legend className="sr-only">Options</legend>
            {item.options.map((option, n) => {
              const chosen = choice === n;
              const right = !!result && option === result.answer;
              const wrong = !!result && chosen && !result.correct;
              return (
                <label
                  key={option}
                  className={`flex cursor-pointer items-center gap-4 border-b border-rule py-3.5 ${
                    right ? "bg-ink px-3 text-paper" : chosen && !result ? "bg-paper-2 px-3" : ""
                  }`}
                >
                  {/* The radio itself, invisible, lies over its letter, so a
                      click or tap lands on it and the letter shows its state. */}
                  <span className="relative size-7 shrink-0">
                    <input
                      type="radio"
                      name={`choice-${item.id}`}
                      checked={chosen}
                      onChange={() => setChoice(n)}
                      className="peer absolute inset-0 size-7 cursor-pointer opacity-0"
                    />
                    <span
                      aria-hidden
                      className={`label flex size-7 items-center justify-center border text-[11px] tracking-normal peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent ${
                        wrong
                          ? "border-accent bg-accent text-on-accent"
                          : right
                            ? "border-paper"
                            : chosen
                              ? "border-ink bg-ink text-paper"
                              : "border-ink"
                      }`}
                    >
                      {LETTERS[n]}
                    </span>
                  </span>
                  <span className={`min-w-0 flex-1 text-[17px] leading-[1.4] ${wrong ? "text-ink-2 line-through" : ""}`}>
                    <MathsText text={option} />
                  </span>
                  {right && <span className="label shrink-0">✓ Answer</span>}
                  {wrong && <span className="label shrink-0">✕ Your choice</span>}
                </label>
              );
            })}
            {!result && (
              <button
                type="button"
                disabled={choice === null || answer.isPending}
                onClick={() => choice !== null && submit({ choice })}
                className={`${button.primary} mt-4 w-fit`}
              >
                Check
              </button>
            )}
          </fieldset>
        )}

        {item.kind === "true_false" && !result && (
          <div className="flex gap-3">
            {[true, false].map((value) => (
              <button
                key={String(value)}
                type="button"
                disabled={answer.isPending}
                onClick={() => submit({ truth: value })}
                className={`${button.outline} min-w-28`}
              >
                {value ? "True" : "False"}
              </button>
            ))}
          </div>
        )}

        {selfMarked && !result && (
          <div className="flex flex-col gap-4">
            {item.kind === "short_answer" && (
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={3}
                maxLength={2000}
                aria-label="Your answer"
                placeholder="Your answer, from memory (optional)"
                className="w-full border border-ink bg-transparent px-3.5 py-3 text-base placeholder:text-ink-3 focus:border-2 focus:border-accent focus:px-[13px] focus:py-[11px] focus:outline-none"
              />
            )}
            {revealed ? (
              <>
                <p className="max-w-[640px] border-l-2 border-ink bg-paper-2 px-4 py-3 text-[17px] leading-[1.6]">
                  <MathsText text={item.answer} />
                </p>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={answer.isPending}
                    onClick={() => submit({ knew: true, text: text || undefined })}
                    className={button.primary}
                  >
                    I knew it
                  </button>
                  <button
                    type="button"
                    disabled={answer.isPending}
                    onClick={() => submit({ knew: false, text: text || undefined })}
                    className={button.outline}
                  >
                    Not yet
                  </button>
                </div>
              </>
            ) : (
              <button type="button" onClick={() => setRevealed(true)} className={`${button.outline} w-fit`}>
                {item.kind === "flashcard" ? "Show the back" : "Show the answer"}
              </button>
            )}
          </div>
        )}

        {answer.error && (
          <p role="alert" className="flex items-center gap-2.5 text-[15px] leading-[1.55]">
            <Mark />
            {answer.error.message}
          </p>
        )}
      </div>

      {result && (
        <div role="status" className="flex flex-col gap-3 border-t border-ink pt-4 desk:border-t-0 desk:border-l desk:pt-1 desk:pl-6">
          <p className="label text-ink-2">Marking</p>
          <p className="display text-[34px] leading-none tracking-[-0.02em] tab:text-[38px]">
            {result.graded_by === "learner"
              ? result.correct
                ? "Marked as known."
                : "Marked as not yet."
              : result.correct
                ? "Right."
                : (
                  <>
                    Not quite.{" "}
                    {/* A multiple choice shows the answer among its options. */}
                    <span
                      className={
                        item.kind === "multiple_choice"
                          ? "sr-only"
                          : "block pt-3 font-sans text-[17px] leading-[1.5] tracking-normal text-ink-2"
                      }
                    >
                      The answer: <MathsText text={result.answer} />
                    </span>
                  </>
                )}
          </p>
          {result.explanation && (
            <p className="text-[15px] leading-relaxed text-ink-2">
              <MathsText text={result.explanation} />
            </p>
          )}
          <CitationChips environmentId={environmentId} citations={result.sources} showFilename />
          <div className="flex flex-col gap-1 border-t border-rule pt-3">
            <p className="label text-ink-2">
              <span aria-hidden>◷ </span>Comes back
            </p>
            <p className="text-[15px] leading-[1.5]">
              {item.concept.name} comes back for review{" "}
              {result.gap_days === 1 ? "tomorrow" : `in ${result.gap_days} days`},{" "}
              {formatDateTime(result.due_at)}.
            </p>
          </div>
          <button type="button" onClick={onNext} className={`${button.primary} mt-2 w-full tab:w-fit`}>
            {last ? "Finish" : "Next"}
          </button>
        </div>
      )}
    </article>
  );
}
