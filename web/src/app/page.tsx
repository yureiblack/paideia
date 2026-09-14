import { ApiStatus } from "@/components/api-status";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-10 px-6 py-24">
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Paideia</h1>
        <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">
          An adaptive learning workspace. Upload material, and the environment
          maintains its own summaries, concept map and roadmap.
        </p>
      </div>
      <ApiStatus />
    </main>
  );
}