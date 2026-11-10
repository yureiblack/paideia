import { KnowledgeMap } from "@/components/knowledge-map";

export default async function KnowledgeMapPage({
  params,
  searchParams,
}: PageProps<"/environments/[id]/knowledge-map">) {
  const { id } = await params;
  const { concept } = await searchParams;
  return (
    <KnowledgeMap
      environmentId={id}
      conceptId={typeof concept === "string" && concept ? concept : null}
    />
  );
}
