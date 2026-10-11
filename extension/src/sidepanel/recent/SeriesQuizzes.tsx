/** The quizzes of one series: write a new one from its slides, or reopen an earlier one. */

import { useCallback, useEffect, useState } from "react";

import type { QuizOut, QuizSummary } from "@shared/types";

import { ApiError, createQuiz, getQuiz, listQuizzes } from "../../shared/api-client";
import { Button } from "../components/Button";
import { relativeTime } from "./library";

type ListState = { status: "loading" } | { status: "loaded"; quizzes: QuizSummary[] } | { status: "error"; message: string };

const LENGTHS = [5, 10];

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

export function SeriesQuizzes({
  seriesId,
  canResearch,
  onOpen,
}: {
  seriesId: string;
  /** Web research for study resources is switched on for this account. */
  canResearch: boolean;
  onOpen: (quiz: QuizOut) => void;
}): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [count, setCount] = useState(LENGTHS[0]);
  const [research, setResearch] = useState(false);
  const [writing, setWriting] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<Problem | null>(null);

  const load = useCallback(async () => {
    try {
      setState({ status: "loaded", quizzes: (await listQuizzes(seriesId)).quizzes });
    } catch (caught) {
      setState({ status: "error", message: errorText(caught) });
    }
  }, [seriesId]);

  useEffect(() => {
    void load();
  }, [load]);

  const write = async () => {
    setWriting(true);
    setError(null);
    try {
      onOpen(await createQuiz(seriesId, { count, research: canResearch && research }));
    } catch (caught) {
      setError(problemFrom(caught));
    } finally {
      setWriting(false);
    }
  };

  const open = async (quizId: string) => {
    setOpening(quizId);
    setError(null);
    try {
      onOpen(await getQuiz(quizId));
    } catch (caught) {
      setError(problemFrom(caught));
    } finally {
      setOpening(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-md border border-slate-200 p-3 shadow-subtle">
        <p className="text-sm text-slate-600">
          A quiz is written from the slides in this series. Get one wrong and you can have it explained.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
            Questions
            <select
              value={count}
              disabled={writing}
              onChange={(event) => setCount(Number(event.target.value))}
              className="rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-indigo-400"
            >
              {LENGTHS.map((length) => (
                <option key={length} value={length}>
                  {length}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void write()} disabled={writing}>
            {writing ? "Writing your quiz…" : "New quiz"}
          </Button>
        </div>
        {canResearch && (
          <label className="flex items-start gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={research}
              disabled={writing}
              onChange={(event) => setResearch(event.target.checked)}
              className="mt-0.5 h-3.5 w-3.5 rounded-sm border-slate-300 text-indigo-600 focus:ring-indigo-400"
            />
            Also search the web for study resources on this topic (slower, admins only for now)
          </label>
        )}
        {writing && (
          <p className="animate-pulse text-xs text-slate-400" role="status">
            {research ? "Reading your slides and searching the web. This can take a minute." : "Reading your slides. This takes a few seconds."}
          </p>
        )}
      </div>

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

      {state.status === "loading" && (
        <ul className="flex animate-pulse flex-col gap-2" aria-hidden="true">
          <li className="h-14 rounded-md bg-slate-100" />
          <li className="h-14 rounded-md bg-slate-100" />
        </ul>
      )}

      {state.status === "error" && (
        <div role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          <p>{state.message}</p>
          <button type="button" onClick={() => void load()} className="mt-2 font-medium underline underline-offset-2">
            Try again
          </button>
        </div>
      )}

      {state.status === "loaded" && state.quizzes.length === 0 && (
        <p className="rounded-md border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
          No quizzes on this series yet.
        </p>
      )}

      {state.status === "loaded" && state.quizzes.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.quizzes.map((quiz) => (
            <li key={quiz.id}>
              <button
                type="button"
                disabled={opening !== null}
                onClick={() => void open(quiz.id)}
                className="flex w-full flex-col gap-1 rounded-md border border-slate-200 bg-white p-3 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100 disabled:opacity-50"
              >
                <span className="line-clamp-1 text-sm font-semibold text-slate-800">{quiz.title}</span>
                <span className="text-xs text-slate-500">
                  {quiz.question_count} questions,{" "}
                  {quiz.best_score === null ? "not taken yet" : `best ${quiz.best_score} of ${quiz.question_count}`}
                </span>
                <span className="text-xs text-slate-400">{relativeTime(new Date(quiz.created_at).getTime())}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
