import { existsSync } from "node:fs";
import path from "node:path";

import type { NextConfig } from "next";

// All configuration lives in one .env at the repository root, one level above
// web/. Next.js only looks inside web/, so load the root file by hand before
// the build reads process.env. Skipped quietly when the file is absent, as it
// is in CI, where real environment variables are used instead.
const rootEnv = path.resolve(process.cwd(), "../.env");
if (existsSync(rootEnv)) process.loadEnvFile(rootEnv);

const nextConfig: NextConfig = {
  agentRules: false,
};

export default nextConfig;
