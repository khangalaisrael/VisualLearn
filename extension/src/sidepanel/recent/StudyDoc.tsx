/** Reading a study guide or a cheat sheet, typeset like a chat answer, with a way to keep it as a note. */

import { useState } from "react";

import type { StudyAidOut } from "@shared/types";

import { createNote } from "../../shared/api-client";
import { downloadMarkdown } from "../../shared/download";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { BackIcon } from "./parts";

type SaveState = "idle" | "saving" | "saved" | "failed";

export function StudyDoc({ aid, onBack }: { aid: StudyAidOut; onBack: () => void }): JSX.Element {
  const [save, setSave] = useState<SaveState>("idle");

  const saveToNotes = async () => {
    setSave("saving");
    try {
      await createNote({ title: aid.title, body: aid.markdown ?? "", source: "ai", series_id: aid.series_id });
      setSave("saved");
    } catch {
      setSave("failed");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={onBack}
        className="-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700"
      >
        <BackIcon />
        Back to the series
      </button>

      <h2 className="text-lg font-semibold leading-snug text-slate-800">{aid.title}</h2>

      {/* A document, not a chat answer: sections are set apart by the space above
          their heading, and the blank line the text has after a heading or a
          list does not add a second gap. */}
      <div className="overflow-x-auto text-sm leading-relaxed text-slate-700 [&>h2:first-child]:mt-0 [&_h1+br]:hidden [&_h2+br]:hidden [&_h2]:mb-1 [&_h2]:mt-5 [&_h2]:text-base [&_h3+br]:hidden [&_h3]:mt-3 [&_ol+br]:hidden [&_ul+br]:hidden">
        <MathText text={aid.markdown ?? ""} />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-4">
        <Button variant="secondary" onClick={() => void saveToNotes()} disabled={save === "saving" || save === "saved"}>
          {save === "saved" ? "Saved to notes" : save === "saving" ? "Saving…" : "Save to notes"}
        </Button>
        <Button variant="secondary" onClick={() => downloadMarkdown(aid.title, aid.markdown ?? "")}>
          Download
        </Button>
        {save === "failed" && (
          <p role="alert" className="text-xs text-red-700 dark:text-red-300">
            Couldn't save. Try again.
          </p>
        )}
        {save === "idle" && <p className="text-xs text-slate-400">A note is kept until you delete it.</p>}
      </div>
    </div>
  );
}
