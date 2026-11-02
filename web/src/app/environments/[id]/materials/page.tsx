import { Materials } from "@/components/materials";

export default async function MaterialsPage({
  params,
}: PageProps<"/environments/[id]/materials">) {
  const { id } = await params;
  return <Materials environmentId={id} />;
}
