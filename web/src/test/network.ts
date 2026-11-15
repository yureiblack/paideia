// A stand-in for the network in component tests. Each test lists the answers
// the API gives, by method and path; every request is recorded, so a test
// can check what was sent. A request nobody planned for fails the test.

import { vi } from "vitest";

type Answer = { status?: number; body?: unknown; headers?: Record<string, string> };
type Route = { method: string; path: string; answer: Answer | ((body: unknown) => Answer) };
export type Sent = { method: string; path: string; search: string; body: unknown };

export function fakeApi(routes: Route[]): Sent[] {
  const sent: Sent[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const url = new URL(input);
      const method = init.method ?? "GET";
      const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
      sent.push({ method, path: url.pathname, search: url.search, body });
      const route = routes.find((r) => r.method === method && r.path === url.pathname);
      if (!route) throw new Error(`No answer planned for ${method} ${url.pathname}`);
      const answer = typeof route.answer === "function" ? route.answer(body) : route.answer;
      const status = answer.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(answer.body), {
        status,
        headers: { "Content-Type": "application/json", ...answer.headers },
      });
    }),
  );
  return sent;
}
