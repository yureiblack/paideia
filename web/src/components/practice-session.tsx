"use client";

// One practice session, one item at a time. Answer first, from memory: a
// choice, true or false, or, for a short answer or flashcard, your own answer
// before revealing the stored one and marking whether you knew it. Then the
// right answer, why, the passages it comes from, and when the item comes
// back. Nothing here is a score: it only decides when items return.

import { useEffect, useRef, useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { useAnswer, usePracticeSession } from "@/hooks/use-practice";
import { formatDateTime } from "@/lib/format";
import type { AttemptInput, AttemptResult, PracticeItem, PracticeKind } from "@/lib/types";

const KIND_LABEL: Record<PracticeKind, string> = {
  short_answer: "Short answer",
  multiple_choice: "Multiple choice",
  true_false: "True or false",
  flashcard: "Flashcard",
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

  if (query.isPending) return <p className="text-zinc-500">Starting practice…</p>;
  if (query.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not start practice: {query.error.message}
      </p>
    );
  }
  const items = query.data;
  const back = (
    <button
      type="button"
      onClick={onDone}
      className="w-fit rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
    >
      Back to practice
    </button>
  );
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Nothing to practise here right now.</p>
        {back}
      </div>
    );
  }
  if (index >= items.length) {
    const tomorrow = results.filter((r) => r.box <= 1).length;
    return (
      <section aria-labelledby="done-heading" className="flex flex-col gap-3">
        <h2 id="done-heading" className="text-lg font-semibold">
          Session done
        </h2>
        <p className="text-sm">
          You practised {items.length} {items.length === 1 ? "item" : "items"}.{" "}
          {tomorrow === items.length
            ? "They all come back tomorrow."
            : tomorrow > 0
              ? `${tomorrow} come back tomorrow, the rest later.`
              : "They come back later."}{" "}
          Each time you recall an item, it comes back further apart.
        </p>
        {back}
      </section>
    );
  }
  const item = items[index];
  return (
    <section aria-labelledby="session-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="session-heading" className="font-medium">
          {title}
        </h2>
        <span className="text-sm text-zinc-500">
          {index + 1} of {items.length}
        </span>
      </div>
      <ItemCard
        key={item.id}
        environmentId={environmentId}
        item={item}
        onAnswered={(result) => setResults([...results, result])}
        onNext={() => setIndex(index + 1)}
        last={index === items.length - 1}
      />
      <button
        type="button"
        onClick={onDone}
        className="w-fit text-sm text-zinc-500 underline underline-offset-2"
      >
        Stop here
      </button>
    </section>
  );
}

function ItemCard({
  environmentId,
  item,
  onAnswered,
  onNext,
  last,
}: {
  environmentId: string;
  item: PracticeItem;
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
    <article className="flex flex-col gap-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {KIND_LABEL[item.kind]} · {item.concept.name}
      </p>
      <p className="text-base font-medium">{item.prompt}</p>

      {item.kind === "multiple_choice" && item.options && (
        <fieldset disabled={!!result} className="flex flex-col gap-2">
          <legend className="sr-only">Options</legend>
          {item.options.map((option, n) => (
            <label key={option} className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name={`choice-${item.id}`}
                checked={choice === n}
                onChange={() => setChoice(n)}
                className="mt-1"
              />
              <span>{option}</span>
            </label>
          ))}
          {!result && (
            <button
              type="button"
              disabled={choice === null || answer.isPending}
              onClick={() => choice !== null && submit({ choice })}
              className="w-fit rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Check
            </button>
          )}
        </fieldset>
      )}

      {item.kind === "true_false" && !result && (
        <div className="flex gap-2">
          {[true, false].map((value) => (
            <button
              key={String(value)}
              type="button"
              disabled={answer.isPending}
              onClick={() => submit({ truth: value })}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
            >
              {value ? "True" : "False"}
            </button>
          ))}
        </div>
      )}

      {selfMarked && !result && (
        <div className="flex flex-col gap-3">
          {item.kind === "short_answer" && (
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={3}
              maxLength={2000}
              aria-label="Your answer"
              placeholder="Your answer, from memory (optional)"
              className="w-full rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
            />
          )}
          {revealed ? (
            <>
              <p className="rounded-lg bg-zinc-100 p-3 text-sm dark:bg-zinc-900">{item.answer}</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={answer.isPending}
                  onClick={() => submit({ knew: true, text: text || undefined })}
                  className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  I knew it
                </button>
                <button
                  type="button"
                  disabled={answer.isPending}
                  onClick={() => submit({ knew: false, text: text || undefined })}
                  className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
                >
                  Not yet
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setRevealed(true)}
              className="w-fit rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
            >
              {item.kind === "flashcard" ? "Show the back" : "Show the answer"}
            </button>
          )}
        </div>
      )}

      {answer.error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {answer.error.message}
        </p>
      )}

      {result && (
        <div role="status" className="flex flex-col gap-2 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
          <p className="font-medium">
            {result.graded_by === "learner"
              ? result.correct
                ? "Marked as known."
                : "Marked as not yet."
              : result.correct
                ? "Right."
                : `Not quite. The answer: ${result.answer}`}
          </p>
          {result.explanation && <p>{result.explanation}</p>}
          <CitationChips environmentId={environmentId} citations={result.sources} showFilename />
          <p className="text-xs text-zinc-500">Comes back {formatDateTime(result.due_at)}.</p>
          <button
            type="button"
            onClick={onNext}
            className="w-fit rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            {last ? "Finish" : "Next"}
          </button>
        </div>
      )}
    </article>
  );
}
