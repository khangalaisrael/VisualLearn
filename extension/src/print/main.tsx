/**
 * The print page behind "Save as PDF" (see shared/print.ts). It shows one
 * document, typeset like the panel shows it, and opens Chrome's print window
 * once the fonts have loaded. Always light: it is a page for paper.
 */

import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";

import { PRINT_DOC_KEY, type PrintDoc } from "../shared/print";
import "../sidepanel/index.css";
import { Button } from "../sidepanel/components/Button";
import { MathText } from "../sidepanel/components/MathText";

type State = { status: "loading" } | { status: "ready"; doc: PrintDoc } | { status: "missing" };

function PrintApp(): JSX.Element {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    chrome.storage.local
      .get(PRINT_DOC_KEY)
      .then((stored) => {
        const doc = stored[PRINT_DOC_KEY] as PrintDoc | undefined;
        setState(doc ? { status: "ready", doc } : { status: "missing" });
      })
      .catch(() => setState({ status: "missing" }));
  }, []);

  // The print window opens by itself, once, when the page is fully laid out.
  // The tab's title becomes the PDF's suggested file name.
  useEffect(() => {
    if (state.status !== "ready") return;
    document.title = state.doc.title;
    let cancelled = false;
    void document.fonts.ready.then(() => {
      requestAnimationFrame(() => {
        if (!cancelled) window.print();
      });
    });
    return () => {
      cancelled = true;
    };
  }, [state]);

  if (state.status === "loading") {
    return <p className="p-8 text-sm text-slate-500">Preparing your document…</p>;
  }

  if (state.status === "missing") {
    return (
      <p className="p-8 text-sm text-slate-600">
        There is nothing to print here. Go back to VisionLearn and press Save as PDF on a note or a study guide.
      </p>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-8 py-3 print:hidden">
        <p className="text-sm text-slate-600">
          In the print window, set <span className="font-medium text-slate-800">Destination</span> to{" "}
          <span className="font-medium text-slate-800">Save as PDF</span>, then press Save.
        </p>
        <Button onClick={() => window.print()}>Open the print window</Button>
      </div>
      <main className="mx-auto max-w-[720px] px-8 py-10 print:max-w-none print:p-0">
        <h1 className="mb-6 text-2xl font-semibold leading-tight text-slate-900">
          <MathText text={state.doc.title} />
        </h1>
        {/* The same spacing rules as a study document in the panel. */}
        <div className="text-[15px] leading-relaxed text-slate-800 [&>h2:first-child]:mt-0 [&_h1+br]:hidden [&_h2+br]:hidden [&_h2]:mb-1 [&_h2]:mt-6 [&_h2]:text-lg [&_h3+br]:hidden [&_h3]:mt-4 [&_ol+br]:hidden [&_ul+br]:hidden">
          <MathText text={state.doc.body} />
        </div>
      </main>
    </>
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("VisionLearn print: #root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <PrintApp />
  </React.StrictMode>
);
