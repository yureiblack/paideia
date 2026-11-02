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
