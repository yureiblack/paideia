// The shapes the backend sends and accepts, mirrored by hand from the Pydantic
// schemas in api/app/schemas.py. If a field changes there, change it here.

export type Environment = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type EnvironmentInput = {
  name: string;
  description: string | null;
};

// PATCH sends only the fields being changed.
export type EnvironmentPatch = Partial<EnvironmentInput>;

// Same limits the backend enforces, so the form can stop over-long input
// before the request is ever sent. The backend still checks.
export const NAME_MAX_LENGTH = 100;
export const DESCRIPTION_MAX_LENGTH = 2000;

// uploaded: waiting to be read. processing: being read now. ready: its pages
// are stored. failed: could not be read; error says why.
export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export type Document = {
  id: string;
  environment_id: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  // Pages with any text. 0 usually means a scanned PDF with no text layer.
  pages_with_text: number | null;
  // The file was damaged and had to be repaired to be read.
  repaired: boolean;
  created_at: string;
  updated_at: string;
};

export type DocumentPage = {
  page_number: number;
  content: string;
};

// The backend's default MAX_UPLOAD_MB. Checked here only to spare a pointless
// upload; the backend enforces its own setting either way.
export const MAX_UPLOAD_MB = 50;

// Where a passage came from: the one shape everything cites with, search
// results now and generated summaries later. document_version is the
// fingerprint (SHA-256) of the document's file; with chunk_id it pins one
// exact passage. filename serves as the title; excerpt is the passage itself.
export type Citation = {
  environment_id: string;
  document_id: string;
  document_version: string;
  filename: string;
  chunk_id: string;
  page_start: number;
  page_end: number;
  heading: string | null;
  excerpt: string;
};

// One passage that matched a search. score is the reranker's judgement of how
// well it answers the query, from 0 to 1: higher is better. It orders
// results; it is not a probability.
export type SearchResult = {
  citation: Citation;
  score: number;
};

// One page a cited passage touches. The passage covers content from
// highlight_start up to, but not including, highlight_end.
export type SourcePage = {
  page_number: number;
  content: string;
  highlight_start: number;
  highlight_end: number;
};

// A citation shown in its place: every page the passage touches, in order.
export type SourcePreview = {
  citation: Citation;
  pages: SourcePage[];
};

// One chunk either search found, with its place at every stage of the search.
// Ranks count from 1; null means that stage never saw the chunk.
// lexical_score: Postgres's text-search rank. semantic_score: cosine
// similarity. fusion_score: the Reciprocal Rank Fusion sum. rerank_score: the
// reranker's 0 to 1. final_rank: its place in the results, if it made them.
export type SearchCandidate = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  heading: string | null;
  lexical_rank: number | null;
  lexical_score: number | null;
  semantic_rank: number | null;
  semantic_score: number | null;
  fusion_score: number;
  rerank_score: number | null;
  final_rank: number | null;
};

// How a search was ranked, sent only when the request asks for it.
export type SearchDebug = {
  top_k_lexical: number;
  top_k_dense: number;
  candidate_pool: number;
  final_k: number;
  candidates: SearchCandidate[];
};

export type SearchResponse = {
  results: SearchResult[];
  debug: SearchDebug | null;
};

// The backend's limit on a search query's length.
export const SEARCH_QUERY_MAX_LENGTH = 500;
