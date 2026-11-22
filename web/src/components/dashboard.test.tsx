// The home screen (decision record 28): a first visit is welcomed with the
// five steps and one action; afterwards Home opens on where the reader left
// off, with the first session of today's plan and the document read last.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { Dashboard } from "@/components/dashboard";
import type { Environment, StudyPlan } from "@/lib/types";
import { fakeApi } from "@/test/network";

const OS: Environment = {
  id: "e1",
  name: "Operating Systems",
  description: "Course notes, weeks 1 to 5.",
  created_at: "2026-11-10T10:00:00Z",
  updated_at: "2026-11-10T10:00:00Z",
};
const ALGEBRA: Environment = { ...OS, id: "e2", name: "Linear Algebra", description: null, updated_at: "2026-11-20T10:00:00Z" };

const PLAN: StudyPlan = {
  sessions: [
    {
      kind: "strengthen",
      title: "Strengthen: round robin scheduling",
      minutes: 1,
      rationale: "Missed on the last answer.",
      concepts: [{ id: "c1", name: "Round robin scheduling" }],
      stage: null,
      document: null,
      needs_preparing: false,
    },
  ],
  later: [],
  minutes: 1,
  budget: null,
};
const EMPTY_PLAN: StudyPlan = { sessions: [], later: [], minutes: 0, budget: null };

function show(environments: Environment[]) {
  fakeApi([
    { method: "GET", path: "/api/environments", answer: { body: environments } },
    { method: "GET", path: "/api/environments/e1/plan", answer: { body: PLAN } },
    { method: "GET", path: "/api/environments/e2/plan", answer: { body: EMPTY_PLAN } },
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: [] } },
    { method: "GET", path: "/api/environments/e2/documents", answer: { body: [] } },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Dashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => window.localStorage.clear());

describe("Dashboard", () => {
  it("welcomes a first visit with the five steps and one action", async () => {
    show([]);
    expect(await screen.findByRole("heading", { level: 1, name: "A library that reads with you." })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create your first environment" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Read the guide" })).toHaveAttribute("href", "/guide");
    const steps = screen.getByRole("region", { name: /How it works/ });
    expect(within(steps).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "Organise",
      "Add",
      "Build",
      "Learn",
      "Return",
    ]);
  });

  it("opens on the environment opened last, with the first session of its plan", async () => {
    window.localStorage.setItem("paideia.last.environment", "e1");
    show([OS, ALGEBRA]);
    const next = await screen.findByRole("region", { name: "Operating Systems" });
    expect(await within(next).findByRole("heading", { name: "Round robin scheduling" })).toBeVisible();
    expect(within(next).getByText("Missed on the last answer.")).toBeVisible();
    expect(within(next).getByRole("link", { name: "Start" })).toHaveAttribute(
      "href",
      "/environments/e1/practice?concepts=c1&title=Strengthen%3A%20round%20robin%20scheduling",
    );
    expect(screen.getByRole("list", { name: "Environments" }).children).toHaveLength(2);
    expect(screen.getByRole("button", { name: "New environment" })).toBeVisible();
  });

  it("opens on the environment changed last when none was opened here", async () => {
    show([OS, ALGEBRA]);
    const next = await screen.findByRole("region", { name: "Linear Algebra" });
    expect(await within(next).findByText(/Nothing planned today/)).toBeVisible();
    expect(within(next).getByRole("link", { name: "Open the environment" })).toHaveAttribute("href", "/environments/e2");
  });

  it("offers to keep reading the document read last", async () => {
    window.localStorage.setItem(
      "paideia.last.reading",
      JSON.stringify({ environmentId: "e1", documentId: "d1", filename: "Week 5.pdf", page: 2, pages: 3 }),
    );
    show([OS]);
    expect(await screen.findByText("Week 5.pdf")).toBeVisible();
    expect(screen.getByText("Operating Systems · page 2 of 3")).toBeVisible();
    expect(screen.getByRole("link", { name: "Resume reading" })).toHaveAttribute(
      "href",
      "/environments/e1/materials/d1#page-2",
    );
  });
});
