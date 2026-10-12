/**
 * Handing something from one part of the side panel to another: code from an
 * answer into the Code tab, and a question from the Code tab into Chat. The
 * panel shell (sidepanel/App.tsx) listens and switches tabs. Pages without a
 * shell (the print page) have no listener, so nothing there offers to hand
 * anything over.
 */

export type CodeLanguage = "haskell" | "java";

export const CODE_LANGUAGES: { id: CodeLanguage; name: string }[] = [
  { id: "haskell", name: "Haskell" },
  { id: "java", name: "Java" },
];

export type Handoff = { kind: "code"; language: CodeLanguage; code: string } | { kind: "chat"; question: string };

const listeners = new Set<(handoff: Handoff) => void>();

/** Called by the panel shell. Returns the function that stops listening. */
export function onHandoff(listener: (handoff: Handoff) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Whether there is anywhere to hand things to (false on the print page). */
export function canHandOff(): boolean {
  return listeners.size > 0;
}

function send(handoff: Handoff): void {
  for (const listener of listeners) listener(handoff);
}

/** The language of a code block, if it is one the Code tab can run. */
export function runnableLanguage(language: string | null | undefined): CodeLanguage | null {
  const name = language?.toLowerCase().trim();
  if (name === "haskell" || name === "hs") return "haskell";
  if (name === "java") return "java";
  return null;
}

export function openInCodeTab(language: CodeLanguage, code: string): void {
  send({ kind: "code", language, code });
}

export function askInChat(question: string): void {
  send({ kind: "chat", question });
}
