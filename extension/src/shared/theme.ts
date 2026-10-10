/**
 * Light / Dark / System. "System" follows the browser's colour scheme; the
 * other two override it, so dark mode doesn't depend on a Chrome or Windows
 * setting the user may not know about. Dark is a `dark` class on <html>
 * (Tailwind's `darkMode: "selector"`). Shared by the side panel and the
 * admin page, and kept in sync through chrome.storage so changing it in
 * Settings updates every open page.
 */

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function parse(value: unknown): ThemeChoice {
  return value === "light" || value === "dark" ? value : "system";
}

function apply(choice: ThemeChoice): void {
  const dark = choice === "dark" || (choice === "system" && systemDark.matches);
  document.documentElement.classList.toggle("dark", dark);
}

export async function getTheme(): Promise<ThemeChoice> {
  try {
    return parse((await chrome.storage.local.get(KEY))[KEY]);
  } catch {
    return "system";
  }
}

export function setTheme(choice: ThemeChoice): Promise<void> {
  return chrome.storage.local.set({ [KEY]: choice });
}

/** Call once before the first render. */
export function initTheme(): void {
  let choice: ThemeChoice = "system";
  apply(choice); // no flash of the wrong theme while storage answers
  void getTheme().then((stored) => {
    choice = stored;
    apply(choice);
  });
  systemDark.addEventListener("change", () => apply(choice));
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[KEY]) {
      choice = parse(changes[KEY].newValue);
      apply(choice);
    }
  });
}
