import { Practice } from "@/components/practice";

export default async function PracticePage({
  params,
  searchParams,
}: PageProps<"/environments/[id]/practice">) {
  const { id } = await params;
  const { stage } = await searchParams;
  const number = typeof stage === "string" ? Number.parseInt(stage, 10) : Number.NaN;
  return <Practice environmentId={id} stage={Number.isNaN(number) ? null : number} />;
}
