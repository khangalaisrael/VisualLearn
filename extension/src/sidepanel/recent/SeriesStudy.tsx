/**
 * The study aids of one series: a study guide, a cheat sheet and flashcards,
 * each written from the series' slides. A series keeps one of each; writing
 * it again replaces the earlier one, after asking, and a guide or cheat sheet
 * can be saved to Notes first. A row says when the series has grown past
 * what its aid was written from.
 */

import { useCallback, useEffect, useState } from "react";

import type { StudyAidKind, StudyAidOut, StudyAidSummary } from "@shared/types";

import { ApiError, createNote, createStudyAid, getStudyAid, listStudyAids } from "../../shared/api-client";
import { Button } from "../components/Button";
import { relativeTime } from "./library";
import { noteTitle } from "./StudyDoc";

const KINDS: { kind: StudyAidKind; name: string; about: string }[] = [
  { kind: "guide", name: "Study guide", about: "The topic explained in order, with a worked example and questions to check yourself." },
  { kind: "cheatsheet", name: "Cheat sheet", about: "Definitions, formulas and rules on one page, for a last look before a test." },
  { kind: "flashcards", name: "Flashcards", about: "Short question-and-answer cards to practise recalling the material." },
];

type ListState =
  | { status: "loading" }
  | { status: "loaded"; aids: StudyAidSummary[]; seriesSlideCount: number }
  | { status: "error"; message: string };

// What an aid read before the whole series was read, and before the count was kept.
const OLD_SLIDE_CAP = 12;

/** Says so when the series has more slides than the aid was written from. */
function behindNote(aid: StudyAidSummary, seriesSlideCount: number): string | null {
  if (aid.slide_count === null) {
    return seriesSlideCount > OLD_SLIDE_CAP
      ? `Written from the newest ${OLD_SLIDE_CAP} of ${seriesSlideCount} slides.`
      : null;
  }
  return aid.slide_count < seriesSlideCount
    ? `Written from ${aid.slide_count} of ${seriesSlideCount} slides.`
    : null;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** What went wrong, and whether it is just the day's allowance being used up (HTTP 429). */
interface Problem {
  message: string;
  limited: boolean;
}

function problemFrom(error: unknown): Problem {
  return { message: errorText(error), limited: error instanceof ApiError && error.status === 429 };
}

export function SeriesStudy({ seriesId, onOpen }: { seriesId: string; onOpen: (aid: StudyAidOut) => void }): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  // The kind being written or opened right now; everything else waits.
  const [working, setWorking] = useState<{ kind: StudyAidKind; task: "writing" | "opening" } | null>(null);
  const [error, setError] = useState<Problem | null>(null);
  // The kind whose "Write again" is waiting for an answer.
  const [confirming, setConfirming] = useState<StudyAidKind | null>(null);

  const load = useCallback(async () => {
    try {
      const listed = await listStudyAids(seriesId);
      setState({ status: "loaded", aids: listed.aids, seriesSlideCount: listed.series_slide_count });
    } catch (caught) {
      setState({ status: "error", message: errorText(caught) });
    }
  }, [seriesId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Writes a new aid of this kind. `keep` is the current one, saved to Notes
   * first; if that fails, nothing is written and nothing is replaced. */
  const write = async (kind: StudyAidKind, keep?: StudyAidSummary) => {
    setConfirming(null);
    setWorking({ kind, task: "writing" });
    setError(null);
    try {
      if (keep) {
        try {
          const current = await getStudyAid(keep.id);
          await createNote({
            title: noteTitle(current),
            body: current.markdown ?? "",
            source: "ai",
            series_id: current.series_id,
          });
        } catch (caught) {
          throw new Error(`Couldn't save the current one to Notes, so nothing was replaced. ${errorText(caught)}`);
        }
      }
      onOpen(await createStudyAid(seriesId, kind));
    } catch (caught) {
      setError(problemFrom(caught));
    } finally {
      setWorking(null);
    }
  };

  const open = async (aid: StudyAidSummary) => {
    setWorking({ kind: aid.kind, task: "opening" });
    setError(null);
    try {
      onOpen(await getStudyAid(aid.id));
    } catch (caught) {
      setError(problemFrom(caught));
    } finally {
      setWorking(null);
    }
  };

  if (state.status === "loading") {
    return (
      <ul className="flex animate-pulse flex-col gap-2" aria-hidden="true">
        {KINDS.map(({ kind }) => (
          <li key={kind} className="h-24 rounded-md bg-slate-100" />
        ))}
      </ul>
    );
  }

  if (state.status === "error") {
    return (
      <div role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
        <p>{state.message}</p>
        <button type="button" onClick={() => void load()} className="mt-2 font-medium underline underline-offset-2">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error && error.limited && (
        <p role="status" className="rounded-md border border-violet-100 bg-violet-50/50 p-3 text-sm text-slate-600">
          {error.message}
        </p>
      )}
      {error && !error.limited && (
        <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          {error.message}
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {KINDS.map(({ kind, name, about }) => {
          const existing = state.aids.find((aid) => aid.kind === kind);
          const writing = working?.kind === kind && working.task === "writing";
          const behind = existing ? behindNote(existing, state.seriesSlideCount) : null;
          return (
            <li key={kind} className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 shadow-subtle">
              <div className="flex flex-col gap-0.5">
                <h3 className="text-sm font-semibold text-slate-800">{name}</h3>
                <p className="text-xs leading-relaxed text-slate-500">{about}</p>
              </div>
              {existing && (
                <p className="text-xs tabular-nums text-slate-400">
                  {existing.card_count !== null && `${existing.known_count} of ${existing.card_count} known, `}
                  written {relativeTime(new Date(existing.created_at).getTime()).toLowerCase()}
                </p>
              )}
              {behind && <p className="text-xs tabular-nums text-amber-700 dark:text-amber-300">{behind}</p>}
              <div className="flex flex-wrap items-center gap-2">
                {existing && (
                  <Button onClick={() => void open(existing)} disabled={working !== null}>
                    {working?.kind === kind && working.task === "opening" ? "Opening…" : kind === "flashcards" ? "Study" : "Open"}
                  </Button>
                )}
                <Button
                  variant={existing ? "secondary" : "primary"}
                  onClick={() => (existing ? setConfirming(kind) : void write(kind))}
                  disabled={working !== null || confirming === kind}
                >
                  {writing ? "Writing…" : existing ? "Write again" : "Write one"}
                </Button>
              </div>
              {existing && confirming === kind && (
                <div role="group" aria-label={`Replace the current ${name.toLowerCase()}?`} className="flex flex-col gap-2 rounded-sm bg-slate-50 p-3">
                  <p className="text-xs leading-relaxed text-slate-600">
                    {kind === "flashcards"
                      ? "This replaces the deck and your progress on it."
                      : "This replaces the current one. Save it to Notes first if you want to keep it."}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    {kind !== "flashcards" && (
                      <Button onClick={() => void write(kind, existing)}>Save to Notes and write again</Button>
                    )}
                    <Button variant={kind === "flashcards" ? "primary" : "secondary"} onClick={() => void write(kind)}>
                      {kind === "flashcards" ? "Write again" : "Write again without saving"}
                    </Button>
                    <Button variant="secondary" onClick={() => setConfirming(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
              {writing && (
                <p className="animate-pulse text-xs text-slate-400" role="status">
                  Reading your slides. A long series can take half a minute.
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-slate-400">
        Study aids are deleted after 30 days, like the slides. Save a guide or cheat sheet to Notes to keep it.
      </p>
    </div>
  );
}
