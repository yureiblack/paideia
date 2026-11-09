import { EnvironmentSummary } from "@/components/environment-summary";

export default async function SummaryPage({
  params,
}: PageProps<"/environments/[id]/summary">) {
  const { id } = await params;
  return <EnvironmentSummary environmentId={id} />;
}
