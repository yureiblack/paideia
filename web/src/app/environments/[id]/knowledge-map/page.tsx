import { ConceptInventory } from "@/components/concept-inventory";

export default async function KnowledgeMapPage({
  params,
}: PageProps<"/environments/[id]/knowledge-map">) {
  const { id } = await params;
  return <ConceptInventory environmentId={id} />;
}
