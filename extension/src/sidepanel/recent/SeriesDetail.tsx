/**
 * One selected series: its cover and name, its slides (lecture and practice
 * apart), and the corrections a student can make when the sorter got it
 * wrong: rename, pick another cover, move a slide elsewhere, delete. A
 * sorted series also has quizzes (SeriesQuizzes.tsx, QuizView.tsx).
 */

import { useState } from "react";

import type { QuizOut } from "@shared/types";

import { useUsage } from "../../shared/usage-store";
import { Button } from "../components/Button";
import { type LibraryCapture, type LibrarySeries, countLabel, coverOf, relativeTime } from "./library";
import { BackIcon, CloseIcon, Cover, ICON_BUTTON, MoreIcon, SlideRow } from "./parts";
import { QuizView } from "./QuizView";
import { SeriesQuizzes } from "./SeriesQuizzes";

const FIELD =
  "w-full rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 transition-colors duration-[120ms] focus:border-indigo-400";
const LINK = "rounded-sm px-2 py-1 text-xs font-medium transition-colors duration-[120ms] disabled:opacity-50";
const NEW_SERIES = "__new__";

export interface SeriesActions {
  openCapture: (capture: LibraryCapture) => void;
  deleteCapture: (capture: LibraryCapture) => void;
  deleteSeries: (series: LibrarySeries) => void;
  rename: (series: LibrarySeries, title: string, category: string) => void;
  setCover: (series: LibrarySeries, capture: LibraryCapture) => void;
  moveToSeries: (capture: LibraryCapture, seriesId: string) => void;
  moveToNewSeries: (capture: LibraryCapture, title: string, category: string) => void;
}

type Section = "slides" | "practice" | "quizzes";

function RenameForm({
  series,
  busy,
  onSave,
  onCancel,
}: {
  series: LibrarySeries;
  busy: boolean;
  onSave: (title: string, category: string) => void;
  onCancel: () => void;
}): JSX.Element {
  const [title, setTitle] = useState(series.title);
  const [category, setCategory] = useState(series.category);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (title.trim() && category.trim()) onSave(title.trim(), category.trim());
      }}
    >
      <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
        Series name
        <input className={FIELD} value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
        Category
        <input className={FIELD} value={category} maxLength={80} onChange={(event) => setCategory(event.target.value)} />
      </label>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !title.trim() || !category.trim()}>
          Save
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function CaptureTools({
  capture,
  series,
  others,
  busy,
  actions,
}: {
  capture: LibraryCapture;
  series: LibrarySeries;
  others: LibrarySeries[];
  busy: boolean;
  actions: SeriesActions;
}): JSX.Element {
  const [target, setTarget] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const isCover = series.coverSlideId === capture.slideId;
  return (
    <div className="flex flex-col gap-3 rounded-sm bg-slate-50 p-3">
      <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
        Move to another series
        <select
          className={FIELD}
          value={target}
          disabled={busy}
          onChange={(event) => {
            const value = event.target.value;
            setTarget(value);
            if (value && value !== NEW_SERIES) actions.moveToSeries(capture, value);
          }}
        >
          <option value="">Choose a series</option>
          {others.map((other) => (
            <option key={other.id} value={other.id}>
              {other.category} / {other.title}
            </option>
          ))}
          <option value={NEW_SERIES}>New series…</option>
        </select>
      </label>
      {target === NEW_SERIES && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (newTitle.trim()) actions.moveToNewSeries(capture, newTitle.trim(), series.category);
          }}
        >
          <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
            New series name
            <input className={FIELD} value={newTitle} maxLength={120} onChange={(event) => setNewTitle(event.target.value)} />
          </label>
          <p className="text-xs text-slate-400">It will sit under {series.category}. You can change that afterwards.</p>
          <Button type="submit" disabled={busy || !newTitle.trim()} className="self-start">
            Move
          </Button>
        </form>
      )}
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          disabled={busy || isCover}
          onClick={() => actions.setCover(series, capture)}
          className={`${LINK} text-slate-600 hover:bg-slate-100`}
        >
          {isCover ? "This is the cover" : "Use as cover"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => actions.deleteCapture(capture)}
          className={`${LINK} text-red-700 hover:bg-red-50 dark:text-red-300`}
        >
          Delete slide
        </button>
      </div>
    </div>
  );
}

export function SeriesDetail({
  series,
  allSeries,
  busy,
  actions,
  onBack,
}: {
  series: LibrarySeries;
  allSeries: LibrarySeries[];
  busy: boolean;
  actions: SeriesActions;
  onBack: () => void;
}): JSX.Element {
  const [section, setSection] = useState<Section>("slides");
  const [renaming, setRenaming] = useState(false);
  const [toolsFor, setToolsFor] = useState<string | null>(null);
  const [quiz, setQuiz] = useState<QuizOut | null>(null);
  const usage = useUsage();

  const lectures = series.captures.filter((capture) => capture.kind !== "practice");
  const practice = series.captures.filter((capture) => capture.kind === "practice");
  const sections: [Section, string][] = [
    ...(lectures.length > 0 ? [["slides", `Slides (${lectures.length})`] as [Section, string]] : []),
    ...(practice.length > 0 ? [["practice", `Practice (${practice.length})`] as [Section, string]] : []),
    // Quizzes are written on the server from a real series.
    ...(series.sorted ? [["quizzes", "Quizzes"] as [Section, string]] : []),
  ];
  // The chosen section can vanish (its last slide moved away): fall back to the first.
  const active = sections.some(([value]) => value === section) ? section : (sections[0]?.[0] ?? "slides");
  const shown = active === "practice" ? practice : lectures;
  const others = allSeries.filter((other) => other.sorted && other.id !== series.id);

  if (quiz) {
    return <QuizView key={quiz.id} quiz={quiz} onBack={() => setQuiz(null)} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={onBack}
        className="-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700"
      >
        <BackIcon />
        All series
      </button>

      <Cover blob={coverOf(series)} title={series.title} className="w-full rounded-md" />

      {renaming ? (
        <RenameForm
          series={series}
          busy={busy}
          onCancel={() => setRenaming(false)}
          onSave={(title, category) => {
            actions.rename(series, title, category);
            setRenaming(false);
          }}
        />
      ) : (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-indigo-600 dark:text-indigo-300">{series.category}</p>
          <h2 className="text-lg font-semibold leading-snug text-slate-800">{series.title}</h2>
          <p className="text-xs text-slate-400">
            {countLabel(series.captures.length, "slide")}, last opened {relativeTime(series.lastActivity).toLowerCase()}
          </p>
          <div className="-ml-2 mt-1 flex gap-1">
            {series.sorted && (
              <button type="button" onClick={() => setRenaming(true)} className={`${LINK} text-slate-600 hover:bg-slate-100`}>
                Rename
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => actions.deleteSeries(series)}
              className={`${LINK} text-red-700 hover:bg-red-50 dark:text-red-300`}
            >
              Delete series
            </button>
          </div>
        </div>
      )}

      {sections.length > 1 && (
        <div className="flex gap-1 rounded-sm bg-slate-100 p-1" role="tablist" aria-label="What to show">
          {sections.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={active === value}
              onClick={() => setSection(value)}
              className={`flex-1 rounded-[6px] px-2 py-1.5 text-xs font-medium transition-colors duration-[120ms] ${
                active === value ? "bg-white text-slate-800 shadow-subtle" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {active === "quizzes" && (
        <SeriesQuizzes seriesId={series.id} canResearch={usage?.is_admin ?? false} onOpen={setQuiz} />
      )}

      <ul className={active === "quizzes" ? "hidden" : "flex flex-col gap-1"}>
        {shown.map((capture) => (
          <li key={capture.slideId} className="flex flex-col gap-1">
            <div className="flex items-center gap-1">
              <SlideRow capture={capture} disabled={busy} onOpen={() => actions.openCapture(capture)} />
              <button
                type="button"
                aria-label={toolsFor === capture.slideId ? "Close slide options" : "Slide options"}
                aria-expanded={toolsFor === capture.slideId}
                onClick={() => setToolsFor(toolsFor === capture.slideId ? null : capture.slideId)}
                className={ICON_BUTTON}
              >
                {toolsFor === capture.slideId ? <CloseIcon /> : <MoreIcon />}
              </button>
            </div>
            {toolsFor === capture.slideId &&
              (series.sorted ? (
                <CaptureTools capture={capture} series={series} others={others} busy={busy} actions={actions} />
              ) : (
                <div className="rounded-sm bg-slate-50 p-3">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => actions.deleteCapture(capture)}
                    className={`${LINK} -ml-2 text-red-700 hover:bg-red-50 dark:text-red-300`}
                  >
                    Delete slide
                  </button>
                </div>
              ))}
          </li>
        ))}
      </ul>
    </div>
  );
}
