"use client";

// The form for both creating and editing an environment. It only collects
// input; the parent decides what submitting means and passes back any error.
// The name is set in the display face, as it appears everywhere else.

import { useState, type FormEvent } from "react";

import {
  DESCRIPTION_MAX_LENGTH,
  NAME_MAX_LENGTH,
  type EnvironmentInput,
} from "@/lib/types";

import { button, Mark } from "./ui";

type EnvironmentFormProps = {
  initial?: EnvironmentInput;
  submitLabel: string;
  isPending: boolean;
  error: Error | null;
  onSubmit: (input: EnvironmentInput) => void;
  onCancel: () => void;
  // Smaller type, for the narrow column beside an environment's pages.
  compact?: boolean;
};

export function EnvironmentForm({
  initial,
  submitLabel,
  isPending,
  error,
  onSubmit,
  onCancel,
  compact = false,
}: EnvironmentFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // Stop the browser's own full-page form submission.
    event.preventDefault();
    onSubmit({ name, description: description.trim() ? description : null });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <label className="flex flex-col gap-2">
        <span className="label">Name</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={NAME_MAX_LENGTH}
          placeholder="Operating Systems"
          className={`display w-full border-b border-ink bg-transparent pt-1 pb-2 placeholder:text-ink-3 focus:border-b-2 focus:border-accent focus:pb-[7px] focus:outline-none ${
            compact ? "text-[26px]" : "text-[34px]"
          }`}
        />
      </label>
      <label className="flex flex-col gap-2">
        <span className="label">
          Description <span className="text-ink-3">(optional)</span>
        </span>
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={DESCRIPTION_MAX_LENGTH}
          rows={3}
          placeholder="What this subject covers"
          className="w-full border border-ink bg-transparent px-3.5 py-3 text-base leading-normal placeholder:text-ink-3 focus:border-2 focus:border-accent focus:px-[13px] focus:py-[11px] focus:outline-none"
        />
      </label>

      {error && (
        <p role="alert" className="label flex items-center gap-2">
          <Mark />
          {error.message}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-5">
        <button type="submit" disabled={isPending || !name.trim()} className={button.primary}>
          {isPending ? "Saving…" : submitLabel}
        </button>
        <button type="button" onClick={onCancel} className={button.link}>
          Cancel
        </button>
      </div>
    </form>
  );
}
