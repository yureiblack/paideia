"use client";

// The form for both creating and editing an environment. It only collects
// input; the parent decides what submitting means and passes back any error.

import { useState, type FormEvent } from "react";

import {
  DESCRIPTION_MAX_LENGTH,
  NAME_MAX_LENGTH,
  type EnvironmentInput,
} from "@/lib/types";

type EnvironmentFormProps = {
  initial?: EnvironmentInput;
  submitLabel: string;
  isPending: boolean;
  error: Error | null;
  onSubmit: (input: EnvironmentInput) => void;
  onCancel: () => void;
};

export function EnvironmentForm({
  initial,
  submitLabel,
  isPending,
  error,
  onSubmit,
  onCancel,
}: EnvironmentFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // Stop the browser's own full-page form submission.
    event.preventDefault();
    onSubmit({ name, description: description.trim() ? description : null });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Name</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={NAME_MAX_LENGTH}
          placeholder="Operating Systems"
          className="rounded-lg border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">
          Description <span className="text-zinc-500">(optional)</span>
        </span>
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={DESCRIPTION_MAX_LENGTH}
          rows={3}
          placeholder="What this subject covers"
          className="rounded-lg border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
        />
      </label>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={isPending || !name.trim()}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {isPending ? "Saving…" : submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
