import { LearningRoadmap } from "@/components/learning-roadmap";

export default async function RoadmapPage({
  params,
}: PageProps<"/environments/[id]/roadmap">) {
  const { id } = await params;
  return <LearningRoadmap environmentId={id} />;
}
