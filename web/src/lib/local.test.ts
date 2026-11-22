// What the browser remembers for the reader (decision record 28): notes put
// away stay away until the guide shows them again, and the place read last
// is kept for Home's "keep reading".

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  NOTES,
  putNoteAway,
  rememberEnvironment,
  rememberReading,
  showNotesAgain,
  useLastEnvironment,
  useLastReading,
  useNoteShown,
  useNotesPutAway,
} from "@/lib/local";

beforeEach(() => window.localStorage.clear());

describe("notes", () => {
  it("shows a note until it is put away, and again once the guide asks", () => {
    const shown = renderHook(() => useNoteShown("roadmap"));
    const away = renderHook(() => useNotesPutAway());
    expect(shown.result.current).toBe(true);
    expect(away.result.current).toBe(0);

    act(() => putNoteAway("roadmap"));
    expect(shown.result.current).toBe(false);
    expect(away.result.current).toBe(1);

    act(() => showNotesAgain());
    expect(shown.result.current).toBe(true);
    expect(away.result.current).toBe(0);
  });

  it("knows every place that has a note", () => {
    expect(NOTES).toEqual([
      "new-environment",
      "first-upload",
      "summary",
      "knowledge-map",
      "roadmap",
      "practice",
    ]);
  });
});

describe("where the reader left off", () => {
  it("keeps the environment opened last and the page read last", () => {
    const environment = renderHook(() => useLastEnvironment());
    const reading = renderHook(() => useLastReading());
    expect(environment.result.current).toBeNull();
    expect(reading.result.current).toBeNull();

    act(() => {
      rememberEnvironment("e1");
      rememberReading({ environmentId: "e1", documentId: "d1", filename: "Week 5.pdf", page: 2, pages: 3 });
    });
    expect(environment.result.current).toBe("e1");
    expect(reading.result.current).toEqual({
      environmentId: "e1",
      documentId: "d1",
      filename: "Week 5.pdf",
      page: 2,
      pages: 3,
    });
  });

  it("ignores what it cannot read", () => {
    window.localStorage.setItem("paideia.last.reading", "{not json");
    const reading = renderHook(() => useLastReading());
    expect(reading.result.current).toBeNull();
  });
});
