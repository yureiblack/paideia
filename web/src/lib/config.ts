// Where the backend lives. Next.js inlines NEXT_PUBLIC_ variables into the
// browser bundle when the app is built, so a different address has to be set
// before `pnpm build`, not at runtime. With nothing set, it falls back to the
// local API, which means development needs no env file at all.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
