/**
 * "Save as PDF" for a note, a study guide or a cheat sheet. The text is handed
 * to a print page (src/print/), which opens in its own tab, typesets it the
 * way the panel does, and brings up Chrome's print window, where "Save as
 * PDF" makes the file. Chrome does the PDF, so formulas stay sharp and the
 * text stays selectable, and nothing is sent anywhere.
 */

/** Where the document waits for the print page to pick it up. Kept until the
 * next one replaces it, so reloading the print tab still shows it. */
export const PRINT_DOC_KEY = "printDoc";

export interface PrintDoc {
  title: string;
  /** Markdown with $math$, as notes and study aids are stored. */
  body: string;
}

export async function openPrintView(title: string, body: string): Promise<void> {
  const doc: PrintDoc = { title, body };
  await chrome.storage.local.set({ [PRINT_DOC_KEY]: doc });
  await chrome.tabs.create({ url: chrome.runtime.getURL("src/print/index.html") });
}
