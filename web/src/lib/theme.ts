// The theme: the learner's choice (auto, light or dark), kept in the
// browser, and the light or dark it resolves to, set on <html> as
// data-theme. Auto follows the system and changes when the system does.

export type ThemeChoice = "auto" | "light" | "dark";

export const THEME_KEY = "paideia-theme";

// Runs in <head> before the first paint, so a dark page never flashes
// light. Kept tiny and self-contained: it cannot import anything.
export const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("${THEME_KEY}");var d=c==="dark"||(c!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch(e){}})()`;

export function readThemeChoice(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

export function applyTheme(choice: ThemeChoice) {
  const dark =
    choice === "dark" ||
    (choice === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

const listeners = new Set<() => void>();

export function saveThemeChoice(choice: ThemeChoice) {
  try {
    if (choice === "auto") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage can be blocked; the choice still applies to this page.
  }
  applyTheme(choice);
  listeners.forEach((listener) => listener());
}

export function subscribeThemeChoice(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
