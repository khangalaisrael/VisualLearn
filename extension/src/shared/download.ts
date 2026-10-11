/**
 * Saves text the student wants to keep outside the extension (a note, a study
 * guide, a cheat sheet) as a Markdown file, through the browser's normal
 * download. Nothing is sent anywhere: the file is made in the page.
 */

const MAX_NAME_CHARS = 80;

/** A file name from a title: characters a file system rejects are dropped. */
export function fileNameFor(title: string): string {
  const cleaned = title
    .replace(/[\\/:*?"<>|$`]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_NAME_CHARS)
    .trim();
  return `${cleaned || "note"}.md`;
}

/** Downloads `body` as a Markdown file headed by `title`. */
export function downloadMarkdown(title: string, body: string): void {
  const blob = new Blob([`# ${title.trim()}\n\n${body.trim()}\n`], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileNameFor(title);
  document.body.appendChild(link);
  link.click();
  link.remove();
  // The download has its own handle on the data once it starts.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
