// One function per backend endpoint. Components never call fetch directly:
// they go through the hooks in src/hooks, which go through these.

import { API_BASE_URL } from "@/lib/config";
import type {
  Environment,
  EnvironmentInput,
  EnvironmentPatch,
} from "@/lib/types";

// A failed request, carrying the HTTP status so callers can tell "not found"
// apart from "the server is down". Status 0 means no response arrived at all.
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationProblem = { loc: (string | number)[]; msg: string };

// FastAPI reports errors in two shapes: {"detail": "Environment not found"},
// or for invalid input a list of problems, each naming the field at fault.
// Both become one readable sentence.
async function errorMessage(response: Response): Promise<string> {
  try {
    const { detail } = (await response.json()) as {
      detail?: string | ValidationProblem[];
    };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((problem) => `${problem.loc.at(-1)}: ${problem.msg}`)
        .join("; ");
    }
  } catch {
    // The body was not JSON; fall through to the generic message.
  }
  return `Request failed with status ${response.status}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      // Only requests that carry a body declare it as JSON. Leaving the header
      // off GET and DELETE spares the browser an extra CORS preflight request.
      headers: init.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    // fetch only throws when no response arrived: the API is down or
    // unreachable. The browser's own wording, "Failed to fetch", says nothing
    // useful to a reader, so replace it.
    throw new ApiError(0, "Could not reach the API. Is the backend running?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  // 204 No Content has no body to parse.
  return (response.status === 204 ? undefined : await response.json()) as T;
}

const environmentPath = (id: string) =>
  `/api/environments/${encodeURIComponent(id)}`;

export const api = {
  listEnvironments: () => request<Environment[]>("/api/environments"),

  getEnvironment: (id: string) => request<Environment>(environmentPath(id)),

  createEnvironment: (input: EnvironmentInput) =>
    request<Environment>("/api/environments", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  updateEnvironment: (id: string, patch: EnvironmentPatch) =>
    request<Environment>(environmentPath(id), {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteEnvironment: (id: string) =>
    request<void>(environmentPath(id), { method: "DELETE" }),
};
