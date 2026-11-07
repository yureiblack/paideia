import { Search } from "@/components/search";

export default async function SearchPage({
  params,
}: PageProps<"/environments/[id]/search">) {
  const { id } = await params;
  return <Search environmentId={id} />;
}
