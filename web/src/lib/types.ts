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
