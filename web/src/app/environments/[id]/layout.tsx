// Wraps every tab of one environment in the shared shell. In this version of
// Next.js, route params arrive as a promise and must be awaited.

import { EnvironmentShell } from "@/components/environment-shell";

export default async function EnvironmentLayout({
  children,
  params,
}: LayoutProps<"/environments/[id]">) {
  const { id } = await params;
  return <EnvironmentShell id={id}>{children}</EnvironmentShell>;
}
