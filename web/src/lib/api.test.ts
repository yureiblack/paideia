// The API client: what a failed request becomes on the page, and what a
// request sends. Every section's error message and Reference come from here.

import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";
import { fakeApi } from "@/test/network";

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("a failed request", () => {
  it("carries the API's message, its status and its request id", async () => {
    fakeApi([
      {
        method: "GET",
        path: "/api/environments/e1",
        answer: {
          status: 404,
          body: { detail: "Environment not found", request_id: "4f2a9c1e77" },
          headers: { "X-Request-ID": "4f2a9c1e77" },
        },
      },
    ]);

    const error = await failure(api.getEnvironment("e1"));

    expect(error.status).toBe(404);
    expect(error.message).toBe("Environment not found");
    expect(error.requestId).toBe("4f2a9c1e77");
  });

  it("turns a list of invalid fields into one sentence", async () => {
    fakeApi([
      {
        method: "POST",
        path: "/api/environments",
        answer: {
          status: 422,
          body: {
            detail: [
              { loc: ["body", "name"], msg: "Field required" },
              { loc: ["body", "description"], msg: "String too long" },
            ],
          },
        },
      },
    ]);

    const error = await failure(api.createEnvironment({ name: "", description: null }));

    expect(error.message).toBe("name: Field required; description: String too long");
    expect(error.requestId).toBeNull();
  });

  it("says only the status when the answer is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })),
    );

    const error = await failure(api.listEnvironments());

    expect(error.message).toBe("Request failed with status 502");
  });

  it("says the API could not be reached when no answer arrived", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const error = await failure(api.listEnvironments());

    expect(error.status).toBe(0);
    expect(error.message).toBe("Could not reach the API. Is the backend running?");
  });
});

describe("a request", () => {
  it("sends JSON with its content type only when it has a body", async () => {
    const sent = fakeApi([
      { method: "GET", path: "/api/environments", answer: { body: [] } },
      {
        method: "POST",
        path: "/api/environments",
        answer: { status: 201, body: { id: "e1", name: "Networks" } },
      },
    ]);
    const fetch = vi.mocked(globalThis.fetch);

    await api.listEnvironments();
    await api.createEnvironment({ name: "Networks", description: null });

    // Without a content type a GET needs no CORS preflight request.
    expect(fetch.mock.calls[0][1]).toEqual({});
    expect(fetch.mock.calls[1][1]?.headers).toEqual({ "Content-Type": "application/json" });
    expect(sent[1].body).toEqual({ name: "Networks", description: null });
  });

  it("resolves to nothing for 204 No Content", async () => {
    fakeApi([{ method: "DELETE", path: "/api/environments/e1", answer: { status: 204 } }]);

    await expect(api.deleteEnvironment("e1")).resolves.toBeUndefined();
  });

  it("escapes ids placed in the path", async () => {
    const sent = fakeApi([
      { method: "GET", path: "/api/environments/a%2Fb", answer: { body: {} } },
    ]);

    await api.getEnvironment("a/b");

    expect(sent[0].path).toBe("/api/environments/a%2Fb");
  });
});
