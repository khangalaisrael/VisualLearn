/**
 * The study aids of one series: a study guide, a cheat sheet and flashcards,
 * each written from the series' slides. A series keeps one of each; writing
 * it again replaces the earlier one.
 */

import { useCallback, useEffect, useState } from "react";

import type { StudyAidKind, StudyAidOut, StudyAidSummary } from "@shared/types";

import { ApiError, createStudyAid, getStudyAid, listStudyAids } from "../../shared/api-client";
import { Button } from "../components/Button";
import { relativeTime } from "./library";

const KINDS: { kind: StudyAidKind; name: string; about: string }[] = [
  { kind: "guide", name: "Study guide", about: "The topic explained in order, with a worked example and questions to check yourself." },
  { kind: "cheatsheet", name: "Cheat sheet", about: "Definitions, formulas and rules on one page, for a last look before a test." },
  { kind: "flashcards", name: "Flashcards", about: "Short question-and-answer cards to practise recalling the material." },
];

type ListState = { status: "loading" } | { status: "loaded"; aids: StudyAidSummary[] } | { status: "error"; message: string };

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

  const load = useCallback(async () => {
    try {
      setState({ status: "loaded", aids: (await listStudyAids(seriesId)).aids });
    } catch (caught) {
      setState({ status: "error", message: errorText(caught) });
    }
  }, [seriesId]);

  useEffect(() => {
    void load();
  }, [load]);

  const write = async (kind: StudyAidKind, existing: StudyAidSummary | undefined) => {
    if (existing) {
      const loss = kind === "flashcards" ? " Your progress on the current deck will be lost." : "";
      if (!window.confirm(`Write a new one? It replaces the current one.${loss}`)) return;
    }
    setWorking({ kind, task: "writing" });
    setError(null);
    try {
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
              <div className="flex flex-wrap items-center gap-2">
                {existing && (
                  <Button onClick={() => void open(existing)} disabled={working !== null}>
                    {working?.kind === kind && working.task === "opening" ? "Opening…" : kind === "flashcards" ? "Study" : "Open"}
                  </Button>
                )}
                <Button
                  variant={existing ? "secondary" : "primary"}
                  onClick={() => void write(kind, existing)}
                  disabled={working !== null}
                >
                  {writing ? "Writing…" : existing ? "Write again" : "Write one"}
                </Button>
              </div>
              {writing && (
                <p className="animate-pulse text-xs text-slate-400" role="status">
                  Reading your slides. This takes a few seconds.
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
