"use client";

// The frame around every section of an environment: its name, the edit and
// delete actions, the contents, and background work. It loads the
// environment once; the sections share that cached copy instead of fetching
// it again. The browser tab's title names the section and the environment:
// React places this <title> in the page's head, and no other title competes
// with it (app/layout.tsx).
//
// One column beside the page on a desktop; on a tablet the same parts sit
// above the page with the contents as a row; on a phone the contents open
// as a full-screen sheet (decision record 25).

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BackgroundWork } from "@/components/background-work";
import { EnvironmentForm } from "@/components/environment-form";
import { EnvironmentTabs, tabLabel, tabNumber } from "@/components/environment-tabs";
import { Loading, Reference } from "@/components/query-states";
import { button, Mark } from "@/components/ui";
import {
  useDeleteEnvironment,
  useEnvironment,
  useUpdateEnvironment,
} from "@/hooks/use-environments";
import { ApiError } from "@/lib/api";
import type { Environment } from "@/lib/types";

export function EnvironmentShell({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const environment = useEnvironment(id);
  const pathname = usePathname();
  const error = environment.error;
  const isMissing =
    error instanceof ApiError && (error.status === 404 || error.status === 422);
  const title = (
    <title>
      {environment.data
        ? `${tabLabel(id, pathname)} · ${environment.data.name} · Paideia`
        : isMissing
          ? "Environment not found · Paideia"
          : "Paideia"}
    </title>
  );

  if (environment.isPending) {
    return (
      <div className="px-5 py-8 tab:px-8 desk:px-12 desk:py-9">
        {title}
        <Loading what="the environment" lines={3} />
      </div>
    );
  }

  if (environment.isError) {
    return (
      <div className="px-5 py-8 tab:px-8 desk:px-12 desk:py-9">
        {title}
        <div role="alert" className="flex max-w-2xl flex-col items-start gap-5">
          <h1 className="display text-[44px] leading-[0.92] tracking-[-0.03em] tab:text-[60px]">
            {isMissing ? "Environment not found." : "Could not load environment."}
          </h1>
          <p className="display text-lg text-ink-2 italic">
            {isMissing
              ? "It may have been deleted, or the link is wrong."
              : environment.error.message}
          </p>
          {!isMissing && <Reference error={environment.error} />}
          <div className="flex flex-wrap items-center gap-5">
            {!isMissing && (
              <button
                type="button"
                onClick={() => void environment.refetch()}
                disabled={environment.isFetching}
                className={button.outline}
              >
                {environment.isFetching ? "Trying again…" : "Try again"}
              </button>
            )}
            <Link href="/" className={button.link}>
              <span aria-hidden>← </span>Back to all environments
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col desk:flex-row">
      {title}
      <EnvironmentAside environment={environment.data} />
      <div className="flex min-w-0 flex-1 flex-col gap-9 px-5 pt-6 pb-14 tab:px-8 tab:pt-8 desk:px-12 desk:pt-9">
        {children}
      </div>
    </div>
  );
}

function EnvironmentAside({ environment }: { environment: Environment }) {
  const pathname = usePathname();
  const [contentsOpen, setContentsOpen] = useState(false);

  // A phone's contents sheet closes once a section is chosen (onNavigate,
  // below), and with Escape.
  useEffect(() => {
    if (!contentsOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setContentsOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [contentsOpen]);

  return (
    <aside className="flex flex-col border-b border-ink px-5 pt-5 pb-0 tab:px-8 tab:pt-6 desk:w-66 desk:shrink-0 desk:gap-7 desk:border-r desk:border-b-0 desk:border-r-rule desk:px-6 desk:py-7">
      <EnvironmentHeader environment={environment} />

      {/* A phone shows where you are and a button to the contents. */}
      <div className="mt-4 flex h-11 items-center gap-3 border-t border-rule tab:hidden">
        <p className="label flex-1">
          {tabNumber(environment.id, pathname)} / {tabLabel(environment.id, pathname)}
        </p>
        <button
          type="button"
          onClick={() => setContentsOpen(true)}
          aria-expanded={contentsOpen}
          className="label border border-ink px-2.5 py-1.5"
        >
          Contents ≡
        </button>
      </div>

      <div
        className={`${
          contentsOpen ? "fixed inset-0 z-40 flex flex-col gap-5 overflow-y-auto bg-paper px-5 pt-4 pb-8" : "hidden"
        } tab:static tab:mt-4 tab:flex tab:border-t tab:border-rule tab:p-0 desk:mt-0 desk:flex-col desk:gap-2 desk:border-0`}
      >
        <div className="flex items-center justify-between tab:hidden">
          <p className="label text-ink-3">Contents</p>
          <button
            type="button"
            onClick={() => setContentsOpen(false)}
            className="label bg-ink px-2.5 py-1.5 text-paper"
          >
            Close ✕
          </button>
        </div>
        <p className="label hidden text-ink-3 desk:block">Contents</p>
        <EnvironmentTabs id={environment.id} onNavigate={() => setContentsOpen(false)} />
      </div>

      <div className="desk:mt-auto">
        <BackgroundWork environmentId={environment.id} />
      </div>
    </aside>
  );
}

function EnvironmentHeader({ environment }: { environment: Environment }) {
  const router = useRouter();
  const update = useUpdateEnvironment(environment.id);
  const remove = useDeleteEnvironment();
  const [isEditing, setIsEditing] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  function closeForm() {
    setIsEditing(false);
    update.reset();
  }

  if (isEditing) {
    return (
      <div className="flex flex-col gap-4">
        <p className="label">Edit environment</p>
        <EnvironmentForm
          compact
          initial={{
            name: environment.name,
            description: environment.description,
          }}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onCancel={closeForm}
          onSubmit={(input) => update.mutate(input, { onSuccess: closeForm })}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Link href="/" className="label w-fit text-ink-3 hover:text-ink">
        <span aria-hidden>← </span>All environments
      </Link>
      <h1 className="display text-[30px] leading-none tracking-[-0.015em] tab:text-[34px] desk:text-[30px]">
        {environment.name}
      </h1>
      <div className="flex gap-4">
        <button type="button" onClick={() => setIsEditing(true)} className="label text-ink-2 hover:text-ink hover:underline">
          Edit
        </button>
        <button
          type="button"
          onClick={() => setIsConfirming(true)}
          aria-expanded={isConfirming}
          className="label text-ink-2 hover:text-ink hover:underline"
        >
          Delete
        </button>
      </div>
      {isConfirming && (
        <div role="alertdialog" aria-labelledby="delete-question" className="flex flex-col gap-4 border border-ink p-4">
          <p className="label flex items-center gap-2">
            <Mark />
            Delete environment
          </p>
          <p id="delete-question" className="display text-[22px] leading-[1.1]">
            Delete “{environment.name}”? This cannot be undone.
          </p>
          <div className="flex flex-wrap items-center gap-5">
            <button
              type="button"
              onClick={() => remove.mutate(environment.id, { onSuccess: () => router.push("/") })}
              disabled={remove.isPending}
              className={button.danger}
            >
              {remove.isPending ? "Deleting…" : "Delete"}
            </button>
            <button type="button" onClick={() => setIsConfirming(false)} className={button.link}>
              Keep it
            </button>
          </div>
          {remove.isError && (
            <p role="alert" className="label flex items-center gap-2">
              <Mark />
              Could not delete: {remove.error.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
