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

// One key point of a summary and the passages it rests on.
export type SummaryPoint = {
  text: string;
  citations: Citation[];
};

// A stored summary of one document, written by the local language model from
// the document's own passages. status: pending (waiting its turn),
// generating, ready or failed (error says why). overview and key_points are
// filled in once ready. model, prompt_versions and source_version record what
// wrote it and from which text; current is false for one kept from an earlier
// text, model or prompt. sections is how many parts the document was read in.
export type SummaryStatus = "pending" | "generating" | "ready" | "failed";

export type Summary = {
  id: string;
  document_id: string;
  status: SummaryStatus;
  error: string | null;
  overview: string | null;
  key_points: SummaryPoint[];
  model: string;
  prompt_versions: string[];
  source_version: string;
  sections: number | null;
  seconds: number | null;
  current: boolean;
  created_at: string;
  updated_at: string;
};

// The current summary, and how many earlier ones are kept.
export type CurrentSummary = Summary & { earlier_versions: number };

// A document an environment summary was built from, as it was then.
export type SourceDocument = {
  document_id: string;
  filename: string;
  document_version: string;
  summary_id: string;
};

// A document an environment summary leaves out, and why.
export type NotIncluded = {
  document_id: string;
  filename: string;
  reason: string;
};

// A summary of a whole environment, built from its documents' summaries.
export type EnvironmentSummary = {
  id: string;
  environment_id: string;
  status: SummaryStatus;
  error: string | null;
  overview: string | null;
  key_points: SummaryPoint[];
  model: string;
  prompt_versions: string[];
  source_version: string;
  based_on: SourceDocument[];
  seconds: number | null;
  current: boolean;
  created_at: string;
  updated_at: string;
};

// Where an environment's summary stands. up_to_date: the summary covers the
// material as it is now. updating: a new one is being written. waiting:
// waiting_for documents are still being read or summarized. stale: the
// material changed and no rebuild was asked for. failed: error says why.
// none: nothing to summarize yet. summary is the newest ready one.
export type EnvironmentSummaryState = {
  state: "up_to_date" | "updating" | "waiting" | "stale" | "failed" | "none";
  waiting_for: number;
  error: string | null;
  summary: EnvironmentSummary | null;
  not_included: NotIncluded[];
  earlier_versions: number;
};

// One concept of an environment, proposed by the language model and
// validated by the backend: its name and definition as shown, aliases, the
// documents it appears in, and the passages that explain it.
export type Concept = {
  id: string;
  name: string;
  normalized_name: string;
  definition: string;
  aliases: string[];
  documents: { document_id: string; filename: string }[];
  evidence: Citation[];
};

// Where a document's concept extraction stands. none: not asked for yet.
// proposed and kept: how many concepts the model proposed, and how many
// passed validation.
export type ExtractionState = {
  document_id: string;
  filename: string;
  document_status: DocumentStatus;
  status: "none" | "pending" | "generating" | "ready" | "failed";
  error: string | null;
  model: string | null;
  prompt_version: string | null;
  proposed: number | null;
  kept: number | null;
};

export type ConceptInventory = {
  concepts: Concept[];
  documents: ExtractionState[];
};

// The knowledge graph: relationships between an environment's concepts,
// found in passages that connect them and classified by the local model.
// source PREREQUISITE_OF target: target builds on source. source PART_OF
// target: source is a part, step or kind of target. RELATED_TO has no
// direction.
export type RelationshipType = "PREREQUISITE_OF" | "RELATED_TO" | "PART_OF";

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  relationship_type: RelationshipType;
  confidence: number;
};

// Where the graph stands, as for the environment's summary. pairs: how many
// pairs of concepts the graph considered; asked: how many of them the model
// was asked about in the last build, the rest being remembered.
export type GraphState = {
  state: "up_to_date" | "updating" | "waiting" | "stale" | "failed" | "none";
  waiting_for: number;
  error: string | null;
  nodes: { id: string; name: string }[];
  edges: GraphEdge[];
  pairs: number | null;
  asked: number | null;
  updated_at: string | null;
};

// A concept next to another. depth: steps away along prerequisites (1 for a
// direct one). evidence: the passages showing a direct relationship.
export type Neighbour = {
  id: string;
  name: string;
  depth: number;
  confidence: number | null;
  evidence: Citation[];
};

export type Neighbourhood = {
  concept: { id: string; name: string };
  definition: string;
  aliases: string[];
  prerequisites: Neighbour[];
  dependents: Neighbour[];
  part_of: Neighbour[];
  parts: Neighbour[];
  related: Neighbour[];
};

// The learning roadmap: the environment's concepts in stages, in the order
// fixed rules give them from the knowledge graph. Only title and description
// come from the local model (written is true); otherwise the title is plain
// and description null. state is about those titles; waiting is for the
// knowledge graph.
export type ConceptRef = { id: string; name: string };

export type RoadmapConcept = {
  id: string;
  name: string;
  definition: string;
  builds_on: ConceptRef[];
  in_cycle: boolean;
  documents: { document_id: string; filename: string }[];
  evidence: Citation[];
};

export type RoadmapStage = {
  number: number;
  title: string;
  description: string | null;
  written: boolean;
  documents: { document_id: string; filename: string }[];
  concepts: RoadmapConcept[];
};

export type RoadmapState = {
  state: "up_to_date" | "updating" | "waiting" | "stale" | "failed" | "none";
  error: string | null;
  stages: RoadmapStage[];
  cycles: { concepts: ConceptRef[] }[];
  updated_at: string | null;
};

// Practice: items written from a concept's passages, checked by the backend.
// state none: never prepared; outdated: its material changed since, so its
// items are no longer practised. items: practised; due: due now.
export type PracticeConcept = {
  concept_id: string;
  name: string;
  state: "none" | "pending" | "generating" | "ready" | "failed" | "outdated";
  error: string | null;
  items: number;
  due: number;
};

export type PracticeOverview = {
  due: number;
  items: number;
  next_due_at: string | null;
  concepts: PracticeConcept[];
};

// An item as shown before answering. prompt is the question, statement or
// flashcard front. answer is sent only for the kinds the learner marks
// themselves (short answer, flashcard), to reveal once they are ready.
export type PracticeKind =
  | "short_answer"
  | "multiple_choice"
  | "true_false"
  | "flashcard";

export type PracticeItem = {
  id: string;
  concept: ConceptRef;
  kind: PracticeKind;
  difficulty: number;
  prompt: string;
  options: string[] | null;
  answer: string | null;
  box: number;
  due_at: string;
};

export type AttemptInput = {
  choice?: number;
  truth?: boolean;
  text?: string;
  knew?: boolean;
  seconds?: number;
};

export type AttemptResult = {
  correct: boolean;
  graded_by: "key" | "learner";
  answer: string;
  explanation: string | null;
  sources: Citation[];
  box: number;
  due_at: string;
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
