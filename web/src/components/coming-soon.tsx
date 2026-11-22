// Placeholder for a tab whose feature arrives in a later phase: its name in
// the display face, and what it will do in a sentence, in the sans.

export function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col gap-2 border-y border-rule py-8">
      <h2 className="display text-[28px] leading-[1.05] tracking-[-0.015em]">{title}</h2>
      <p className="max-w-[640px] text-[15px] leading-[1.55] text-ink-2">{description}</p>
    </div>
  );
}
