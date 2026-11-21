"use client";

// Auto, light or dark, in the masthead. On a phone one button steps through
// the three; wider screens show all three with the chosen one underlined.

import { useEffect, useSyncExternalStore } from "react";

import {
  applyTheme,
  readThemeChoice,
  saveThemeChoice,
  subscribeThemeChoice,
  type ThemeChoice,
} from "@/lib/theme";

const CHOICES: { value: ThemeChoice; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeToggle() {
  // The server cannot know the choice; it renders "auto" and the page
  // corrects itself as soon as it runs.
  const choice = useSyncExternalStore(subscribeThemeChoice, readThemeChoice, () => "auto" as const);

  // Auto follows the system while the page is open.
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => {
      if (readThemeChoice() === "auto") applyTheme("auto");
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);

  const index = CHOICES.findIndex((c) => c.value === choice);
  const next = CHOICES[(index + 1) % CHOICES.length];

  return (
    <>
      <button
        type="button"
        onClick={() => saveThemeChoice(next.value)}
        aria-label={`Theme: ${CHOICES[index].label}. Change to ${next.label}`}
        className="label border-b border-ink pb-0.5 tab:hidden"
      >
        {CHOICES[index].label}
      </button>
      <div role="group" aria-label="Theme" className="hidden items-center gap-2.5 tab:flex">
        {CHOICES.map(({ value, label }, i) => (
          <span key={value} className="flex items-center gap-2.5">
            {i > 0 && (
              <span aria-hidden className="label text-ink-3">
                /
              </span>
            )}
            <button
              type="button"
              onClick={() => saveThemeChoice(value)}
              aria-pressed={choice === value}
              className={`label pb-0.5 ${
                choice === value ? "border-b border-ink text-ink" : "text-ink-3 hover:text-ink"
              }`}
            >
              {label}
            </button>
          </span>
        ))}
      </div>
    </>
  );
}
