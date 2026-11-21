// Placeholder for a tab whose feature arrives in a later phase.

export function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="border-y border-rule py-8">
      <h2 className="font-semibold">{title}</h2>
      <p className="display mt-1 text-lg text-ink-2 italic">{description}</p>
    </div>
  );
}
