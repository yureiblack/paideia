import { Practice } from "@/components/practice";

export default async function PracticePage({
  params,
  searchParams,
}: PageProps<"/environments/[id]/practice">) {
  const { id } = await params;
  const { stage, concepts, title } = await searchParams;
  const number = typeof stage === "string" ? Number.parseInt(stage, 10) : Number.NaN;
  const focus =
    typeof concepts === "string" && concepts
      ? {
          conceptIds: concepts.split(","),
          title: typeof title === "string" && title ? title : "Practice",
        }
      : null;
  return (
    <Practice
      environmentId={id}
      stage={Number.isNaN(number) ? null : number}
      focus={focus}
    />
  );
}
