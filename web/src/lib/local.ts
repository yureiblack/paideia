// Small things this browser remembers for the reader (decision record 28):
// which notes were put away, the environment opened last and the page of
// the document read last. They are conveniences, never data: storage may be
// unavailable (a private window, a blocked site), and then they last for
// the visit only, held in memory.

import { useSyncExternalStore } from "react";

const CHANGED = "paideia-local";
const memory = new Map<string, string | null>();

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}

export function write(key: string, value: string | null) {
  memory.set(key, value);
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage may be unavailable; memory keeps it for this visit.
  }
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

// A stored string, or null. The server renders as if nothing were stored
// (serverValue), and the browser takes over with what it remembers.
export function useStored(key: string, serverValue: string | null = null): string | null {
  return useSyncExternalStore(
    subscribe,
    () => read(key),
    () => serverValue,
  );
}

function parse<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

// Notes that explain a place the first time it is opened (components/note).
// A note put away stays away in this browser until the guide shows them all
// again.
export const NOTES = [
  "new-environment",
  "first-upload",
  "summary",
  "knowledge-map",
  "roadmap",
  "practice",
] as const;
export type NoteId = (typeof NOTES)[number];

const noteKey = (id: NoteId) => `paideia.note.${id}`;
// The server renders no note ("put away"), so a note never flashes before
// the browser knows whether it was put away.
const AWAY = "away";

export function useNoteShown(id: NoteId): boolean {
  return useStored(noteKey(id), AWAY) !== AWAY;
}

export function putNoteAway(id: NoteId) {
  write(noteKey(id), AWAY);
}

// How many notes are put away, for the guide's "show them again".
export function useNotesPutAway(): number {
  return useSyncExternalStore(
    subscribe,
    () => NOTES.filter((id) => read(noteKey(id)) === AWAY).length,
    () => 0,
  );
}

export function showNotesAgain() {
  for (const id of NOTES) write(noteKey(id), null);
}

// Where the reader left off: the environment opened last, and the document
// and page read last.
export type LastReading = {
  environmentId: string;
  documentId: string;
  filename: string;
  page: number;
  pages: number;
};

const LAST_ENVIRONMENT = "paideia.last.environment";
const LAST_READING = "paideia.last.reading";

export function rememberEnvironment(id: string) {
  if (read(LAST_ENVIRONMENT) !== id) write(LAST_ENVIRONMENT, id);
}

export function useLastEnvironment(): string | null {
  return useStored(LAST_ENVIRONMENT);
}

export function rememberReading(reading: LastReading) {
  const value = JSON.stringify(reading);
  if (read(LAST_READING) !== value) write(LAST_READING, value);
}

export function useLastReading(): LastReading | null {
  return parse<LastReading>(useStored(LAST_READING));
}

export function forgetReading() {
  write(LAST_READING, null);
}
