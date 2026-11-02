// One function per backend endpoint. Components never call fetch directly:
// they go through the hooks in src/hooks, which go through these.

import { API_BASE_URL } from "@/lib/config";
import type {
  Document,
  DocumentPage,
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
    response = await fetch(`${API_BASE_URL}${path}`, init);
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

// A request carrying JSON. Only requests with a body declare a content type:
// leaving it off GET and DELETE spares the browser a CORS preflight request.
function withJson(method: string, body: unknown): RequestInit {
  return {
    method,
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

const environmentPath = (id: string) =>
  `/api/environments/${encodeURIComponent(id)}`;
const documentPath = (id: string) =>
  `/api/documents/${encodeURIComponent(id)}`;

export const api = {
  listEnvironments: () => request<Environment[]>("/api/environments"),

  getEnvironment: (id: string) => request<Environment>(environmentPath(id)),

  createEnvironment: (input: EnvironmentInput) =>
    request<Environment>("/api/environments", withJson("POST", input)),

  updateEnvironment: (id: string, patch: EnvironmentPatch) =>
    request<Environment>(environmentPath(id), withJson("PATCH", patch)),

  deleteEnvironment: (id: string) =>
    request<void>(environmentPath(id), { method: "DELETE" }),

  listDocuments: (environmentId: string) =>
    request<Document[]>(`${environmentPath(environmentId)}/documents`),

  // The PDF travels as the raw request body, not inside a form, so the
  // backend can stop an oversized upload part-way. The browser announces the
  // file's size up front, which lets it refuse one before any byte is sent.
  uploadDocument: (environmentId: string, file: File) =>
    request<Document>(
      `${environmentPath(environmentId)}/documents?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        body: file,
        headers: { "Content-Type": "application/pdf" },
      },
    ),

  getPages: (documentId: string) =>
    request<DocumentPage[]>(`${documentPath(documentId)}/pages`),

  reprocessDocument: (documentId: string) =>
    request<Document>(`${documentPath(documentId)}/reprocess`, {
      method: "POST",
    }),

  deleteDocument: (documentId: string) =>
    request<void>(documentPath(documentId), { method: "DELETE" }),
};
