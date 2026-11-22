"use client";

// The cells of a computed exercise (decision record 27): a number, a vector,
// a matrix, a few vectors, a choice with weights, or eigenvalues with an
// eigenvector each. Numbers are typed as integers, fractions like 3/4 or
// decimals; the backend reads them exactly and never evaluates them. Once
// marked, each cell shows whether it was right.

import { useState, type FormEvent, type ReactNode } from "react";

import { MathsText } from "@/components/maths-text";
import { button } from "@/components/ui";
import type { ExerciseForm as Form } from "@/lib/types";

// How many cells a form sends, in the order the backend reads them.
export function cellCount(form: Form, choice: number | null): number {
  switch (form.type) {
    case "number":
      return 1;
    case "vector":
      return form.size;
    case "matrix":
      return form.rows * form.columns;
    case "vectors":
      return form.count * form.size;
    case "independence":
      return choice === 1 ? form.size : 0;
    case "eigen":
      return form.size + form.size * form.size;
  }
}

function Cell({
  value,
  onChange,
  label,
  right,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  right: boolean | undefined;
  disabled: boolean;
}) {
  return (
    <input
      type="text"
      inputMode="text"
      autoComplete="off"
      spellCheck={false}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      aria-label={label}
      aria-invalid={right === false || undefined}
      maxLength={24}
      className={`w-16 border-b bg-transparent pb-1 text-center text-base tabular-nums focus:border-b-2 focus:border-accent focus:pb-[3px] focus:outline-none disabled:opacity-100 ${
        right === false ? "border-accent text-accent line-through" : "border-ink"
      }`}
    />
  );
}

// Big brackets around a grid of cells, as a matrix is written.
function Brackets({ columns, children }: { columns: number; children: ReactNode }) {
  return (
    <div
      className="relative grid w-fit gap-x-3 gap-y-2 px-3 py-1 before:absolute before:inset-y-0 before:left-0 before:w-1.5 before:border before:border-r-0 before:border-ink after:absolute after:inset-y-0 after:right-0 after:w-1.5 after:border after:border-l-0 after:border-ink"
      style={{ gridTemplateColumns: `repeat(${columns}, auto)` }}
    >
      {children}
    </div>
  );
}

export function ExerciseForm({
  form,
  pending,
  right,
  onSubmit,
}: {
  form: Form;
  pending: boolean;
  // Once marked: whether each cell was right, in order.
  right: boolean[] | null;
  onSubmit: (cells: string[], choice: number | undefined) => void;
}) {
  const [choice, setChoice] = useState<number | null>(null);
  const count = cellCount(form, choice);
  const [cells, setCells] = useState<string[]>(() =>
    Array.from({ length: cellCount(form, 1) }, () => ""),
  );
  const marked = right !== null;
  const ready =
    (form.type !== "independence" || choice !== null) &&
    cells.slice(0, count).every((c) => c.trim() !== "");

  function cell(index: number, label: string) {
    return (
      <Cell
        key={index}
        value={cells[index] ?? ""}
        onChange={(value) => setCells(cells.map((c, i) => (i === index ? value : c)))}
        label={label}
        right={right?.[index]}
        disabled={marked || pending}
      />
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!ready || marked) return;
    onSubmit(
      cells.slice(0, count).map((c) => c.trim()),
      form.type === "independence" ? (choice ?? undefined) : undefined,
    );
  }

  let fields: ReactNode;
  switch (form.type) {
    case "number":
      fields = (
        <div className="flex items-baseline gap-3 text-xl">
          {form.label && <MathsText text={`\\(${form.label} =\\)`} />}
          {cell(0, "Your answer")}
        </div>
      );
      break;
    case "vector":
      fields = (
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-3 text-xl">
          {Array.from({ length: form.size }, (_, i) => {
            const name = form.labels?.[i] ?? `x_{${i + 1}}`;
            return (
              <span key={i} className="flex items-baseline gap-2">
                <MathsText text={`\\(${name} =\\)`} />
                {cell(i, name)}
              </span>
            );
          })}
        </div>
      );
      break;
    case "matrix":
      fields = (
        <Brackets columns={form.columns}>
          {Array.from({ length: form.rows * form.columns }, (_, i) =>
            cell(i, `Row ${Math.floor(i / form.columns) + 1}, column ${(i % form.columns) + 1}`),
          )}
        </Brackets>
      );
      break;
    case "vectors":
      fields = (
        <div className="flex flex-wrap gap-6">
          {Array.from({ length: form.count }, (_, v) => (
            <Brackets key={v} columns={1}>
              {Array.from({ length: form.size }, (_, i) =>
                cell(v * form.size + i, `Vector ${v + 1}, entry ${i + 1}`),
              )}
            </Brackets>
          ))}
        </div>
      );
      break;
    case "independence":
      fields = (
        <div className="flex flex-col gap-4">
          <fieldset disabled={marked || pending} className="flex flex-wrap gap-3">
            <legend className="sr-only">Independent or dependent</legend>
            {form.options.map((option, n) => (
              <label
                key={option}
                className={`${button.outline} cursor-pointer ${choice === n ? "bg-ink text-paper" : ""}`}
              >
                <input
                  type="radio"
                  name="independence"
                  checked={choice === n}
                  onChange={() => setChoice(n)}
                  className="sr-only"
                />
                {option}
              </label>
            ))}
          </fieldset>
          {choice === 1 && (
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-3 text-xl">
              {Array.from({ length: form.size }, (_, i) => (
                <span key={i} className="flex items-baseline gap-2">
                  <MathsText text={`\\(c_{${i + 1}} =\\)`} />
                  {cell(i, `c${i + 1}`)}
                </span>
              ))}
            </div>
          )}
        </div>
      );
      break;
    case "eigen":
      fields = (
        <div className="flex flex-col gap-5">
          {Array.from({ length: form.size }, (_, k) => (
            <div key={k} className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xl">
              <span className="flex items-baseline gap-2">
                <MathsText text={`\\(\\lambda_{${k + 1}} =\\)`} />
                {cell(k, `Eigenvalue ${k + 1}`)}
              </span>
              <span className="label text-[10px] text-ink-3">eigenvector</span>
              <Brackets columns={1}>
                {Array.from({ length: form.size }, (_, i) =>
                  cell(form.size + k * form.size + i, `Eigenvector ${k + 1}, entry ${i + 1}`),
                )}
              </Brackets>
            </div>
          ))}
        </div>
      );
      break;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5 border-t border-ink pt-5">
      {fields}
      {!marked && (
        <div className="flex flex-wrap items-center gap-5">
          <button type="submit" disabled={!ready || pending} className={button.primary}>
            Check
          </button>
          <span className="label text-[10px] text-ink-3">
            Integers, fractions like 3/4, or decimals
          </span>
        </div>
      )}
    </form>
  );
}
