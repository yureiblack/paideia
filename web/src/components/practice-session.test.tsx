// A practice session from the learner's side (decision record 15): answer
// first, from memory, then see the right answer, where it comes from and when
// the concept comes back. What is sent to the API decides the review schedule,
// so the tests check it too.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PracticeSession } from "@/components/practice-session";
import type { AttemptResult, PracticeItem } from "@/lib/types";
import { fakeApi } from "@/test/network";

const concept = { id: "c1", name: "Threads" };

const choiceItem: PracticeItem = {
  id: "i1",
  concept,
  kind: "multiple_choice",
  difficulty: 1,
  prompt: "What do the threads of one process share?",
  options: ["Nothing", "An address space", "A stack"],
  answer: null,
  box: 0,
  due_at: "2026-11-15T09:00:00Z",
};

const shortItem: PracticeItem = {
  id: "i2",
  concept,
  kind: "short_answer",
  difficulty: 2,
  prompt: "Why is switching threads cheaper than switching processes?",
  options: null,
  answer: "The address space stays the same, so no page tables change.",
  box: 0,
  due_at: "2026-11-15T09:00:00Z",
};

const exerciseItem: PracticeItem = {
  id: "i3",
  concept: { id: "c2", name: "Determinant" },
  kind: "exercise",
  difficulty: 3,
  prompt: "Find the determinant of \\[A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}.\\]",
  options: null,
  answer: null,
  box: 0,
  due_at: "2026-11-15T09:00:00Z",
  exercise: { type: "determinant", variant: 2, form: { type: "number", label: "\\det A" } },
};

function result(overrides: Partial<AttemptResult>): AttemptResult {
  return {
    correct: true,
    graded_by: "key",
    answer: "",
    explanation: null,
    sources: [],
    box: 1,
    due_at: "2026-11-16T09:00:00Z",
    gap_days: 1,
    ...overrides,
  };
}

function start(items: PracticeItem[], answers: Record<string, AttemptResult>) {
  const sent = fakeApi([
    { method: "GET", path: "/api/environments/e1/practice/session", answer: { body: items } },
    ...items.map((item) => ({
      method: "POST",
      path: `/api/learning-items/${item.id}/attempts`,
      answer: { status: 201, body: answers[item.id] },
    })),
  ]);
  const onDone = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PracticeSession
        environmentId="e1"
        conceptIds={null}
        started={1}
        title="Review due today"
        onDone={onDone}
      />
    </QueryClientProvider>,
  );
  return { sent, onDone };
}

describe("PracticeSession", () => {
  it("checks a choice, then shows the answer, its source and when it comes back", async () => {
    const { sent } = start([choiceItem], {
      i1: result({
        correct: false,
        answer: "An address space",
        explanation: "Threads run in their process's memory.",
        sources: [
          {
            environment_id: "e1",
            document_id: "d1",
            document_version: "v1",
            filename: "Week 6 threads.pdf",
            chunk_id: "k1",
            page_start: 3,
            page_end: 3,
            heading: "Threads",
            excerpt: "Threads of a process share its address space.",
          },
        ],
      }),
    });

    expect(await screen.findByText(choiceItem.prompt)).toBeInTheDocument();
    expect(screen.getByText("1 of 1")).toBeInTheDocument();
    const check = screen.getByRole("button", { name: "Check" });
    expect(check).toBeDisabled(); // nothing chosen yet

    await userEvent.click(screen.getByRole("radio", { name: "Nothing" }));
    await userEvent.click(check);

    const outcome = await screen.findByRole("status");
    expect(outcome).toHaveTextContent("Not quite. The answer: An address space");
    expect(outcome).toHaveTextContent("Threads run in their process's memory.");
    expect(outcome).toHaveTextContent("Week 6 threads.pdf");
    expect(outcome).toHaveTextContent("Threads comes back for review tomorrow");
    const attempt = sent.find((s) => s.method === "POST");
    expect(attempt?.path).toBe("/api/learning-items/i1/attempts");
    expect(attempt?.body).toEqual({ choice: 0, seconds: expect.any(Number) });
  });

  it("marks an exercise by its numbers and shows its worked solution", async () => {
    const { sent } = start([exerciseItem], {
      i3: result({
        correct: false,
        answer: "\\(\\det A = -2\\)",
        right: [false],
        steps: ["\\[\\det A = (1)(4) - (2)(3) = -2\\]"],
      }),
    });

    await userEvent.type(await screen.findByRole("textbox", { name: "Your answer" }), "-3");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Not quite. The answer:");
    const worked = screen.getByRole("region", { name: "Worked solution" });
    expect(worked.querySelectorAll("li")).toHaveLength(1);
    expect(worked.querySelector(".katex")).not.toBeNull();
    expect(screen.getByRole("textbox", { name: "Your answer" })).toHaveAttribute("aria-invalid", "true");
    expect(sent.find((s) => s.method === "POST")?.body).toEqual({
      cells: ["-3"],
      variant: 2,
      seconds: expect.any(Number),
    });
  });

  it("lets the learner mark a short answer after seeing the stored one", async () => {
    const { sent } = start([shortItem], {
      i2: result({ graded_by: "learner", answer: shortItem.answer!, gap_days: 3 }),
    });

    await userEvent.type(await screen.findByRole("textbox", { name: "Your answer" }), "No page tables change");
    // The stored answer stays hidden until asked for.
    expect(screen.queryByText(shortItem.answer!)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the answer" }));
    expect(screen.getByText(shortItem.answer!)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I knew it" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Marked as known.");
    expect(screen.getByRole("status")).toHaveTextContent("comes back for review in 3 days");
    expect(sent.find((s) => s.method === "POST")?.body).toEqual({
      knew: true,
      text: "No page tables change",
      seconds: expect.any(Number),
    });
  });

  it("ends with what the answers mean for the next reviews", async () => {
    const { onDone } = start([choiceItem, { ...shortItem, kind: "flashcard" }], {
      i1: result({ correct: true, gap_days: 3 }),
      i2: result({ graded_by: "learner", correct: false, gap_days: 1 }),
    });

    await userEvent.click(await screen.findByRole("radio", { name: "An address space" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Right.");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the back" }));
    await userEvent.click(screen.getByRole("button", { name: "Not yet" }));
    await screen.findByRole("status");
    await userEvent.click(screen.getByRole("button", { name: "Finish" }));

    expect(screen.getByRole("heading", { name: "Session done" })).toBeInTheDocument();
    expect(
      screen.getByText(/1 of your answers bring their concept back tomorrow; the rest later\./),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back to practice" }));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("says when there is nothing to practise", async () => {
    start([], {});

    expect(await screen.findByText("Nothing to practise here right now.")).toBeInTheDocument();
  });
});
