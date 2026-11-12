// One function per backend endpoint. Components never call fetch directly:
// they go through the hooks in src/hooks, which go through these.

import { API_BASE_URL } from "@/lib/config";
import type {
  Document,
  DocumentPage,
  ConceptInventory,
  CurrentSummary,
  Environment,
  EnvironmentInput,
  EnvironmentPatch,
  EnvironmentSummaryState,
  GraphState,
  Neighbourhood,
  AttemptInput,
  AttemptResult,
  PracticeItem,
  PracticeOverview,
  RoadmapState,
  StudyPlan,
  SearchResponse,
  SourcePreview,
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

  getEnvironmentSummary: (environmentId: string) =>
    request<EnvironmentSummaryState>(`${environmentPath(environmentId)}/summary`),

  // Bring the environment's summary up to date, or try again after a failure.
  requestEnvironmentSummary: (environmentId: string) =>
    request<EnvironmentSummaryState>(`${environmentPath(environmentId)}/summary`, {
      method: "POST",
    }),

  getConcepts: (environmentId: string) =>
    request<ConceptInventory>(`${environmentPath(environmentId)}/concepts`),

  requestConcepts: (documentId: string) =>
    request<unknown>(`${documentPath(documentId)}/concepts`, { method: "POST" }),

  getGraph: (environmentId: string) =>
    request<GraphState>(`${environmentPath(environmentId)}/graph`),

  // Bring the graph up to date, or try again after a failure.
  requestGraph: (environmentId: string) =>
    request<GraphState>(`${environmentPath(environmentId)}/graph`, {
      method: "POST",
    }),

  getNeighbourhood: (conceptId: string) =>
    request<Neighbourhood>(
      `/api/concepts/${encodeURIComponent(conceptId)}/neighbourhood`,
    ),

  getRoadmap: (environmentId: string) =>
    request<RoadmapState>(`${environmentPath(environmentId)}/roadmap`),

  // Write the titles of the roadmap's current stages, or try again.
  requestRoadmap: (environmentId: string) =>
    request<RoadmapState>(`${environmentPath(environmentId)}/roadmap`, {
      method: "POST",
    }),

  // until: the end of the learner's day, so "due today" is their today.
  getPractice: (environmentId: string, until: string) =>
    request<PracticeOverview>(
      `${environmentPath(environmentId)}/practice?until=${encodeURIComponent(until)}`,
    ),

  // Write practice items for these concepts, in the background.
  preparePractice: (environmentId: string, conceptIds: string[]) =>
    request<PracticeOverview>(
      `${environmentPath(environmentId)}/practice`,
      withJson("POST", { concept_ids: conceptIds }),
    ),

  // A session: the items of the concepts due today, or with concept ids (a
  // stage) theirs.
  getPracticeSession: (environmentId: string, until: string, conceptIds?: string[]) => {
    const query = new URLSearchParams({ until });
    for (const id of conceptIds ?? []) query.append("concept_id", id);
    const suffix = `?${query}`;
    return request<PracticeItem[]>(
      `${environmentPath(environmentId)}/practice/session${suffix}`,
    );
  },

  answerItem: (itemId: string, input: AttemptInput) =>
    request<AttemptResult>(
      `/api/learning-items/${encodeURIComponent(itemId)}/attempts`,
      withJson("POST", input),
    ),

  // Today's plan; until is the end of the learner's day, minutes an
  // optional time budget.
  getPlan: (environmentId: string, until: string, minutes: number | null) => {
    const query = new URLSearchParams({ until });
    if (minutes) query.set("minutes", String(minutes));
    return request<StudyPlan>(`${environmentPath(environmentId)}/plan?${query}`);
  },

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

  // The document's current summary, or null if none has been asked for.
  getSummary: async (documentId: string) => {
    try {
      return await request<CurrentSummary>(`${documentPath(documentId)}/summary`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  // Make sure the document has a summary: returns it if ready, otherwise the
  // waiting one, which the server then writes in the background.
  requestSummary: (documentId: string) =>
    request<CurrentSummary>(`${documentPath(documentId)}/summary`, {
      method: "POST",
    }),

  deleteDocument: (documentId: string) =>
    request<void>(documentPath(documentId), { method: "DELETE" }),

  getPreview: (chunkId: string) =>
    request<SourcePreview>(`/api/chunks/${encodeURIComponent(chunkId)}/preview`),

  // debug asks for every candidate and its score at each stage.
  search: (environmentId: string, query: string, debug = false) =>
    request<SearchResponse>(
      "/api/search",
      withJson("POST", { environment_id: environmentId, query, debug }),
    ),
};
