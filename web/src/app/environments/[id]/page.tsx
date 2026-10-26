import { EnvironmentOverview } from "@/components/environment-overview";

export default async function OverviewPage({
  params,
}: PageProps<"/environments/[id]">) {
  const { id } = await params;
  return <EnvironmentOverview id={id} />;
}
