/**
 * Recent: the user's captures as a searchable library of series (see
 * recent/library.ts for where the data comes from). A series unfolds in
 * place, or opens as its own page (recent/SeriesDetail.tsx). How long things
 * are kept comes from the server, never hardcoded here.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  deleteSeries,
  deleteSlide,
  getConversation,
  getSlide,
  moveSlide,
  signInWithGoogle,
  updateSeries,
} from "../../shared/api-client";
import { deleteCaptures } from "../../shared/capture-store";
import { Button } from "../components/Button";
import {
  type Library,
  type LibraryCapture,
  type LibrarySeries,
  categoriesOf,
  countLabel,
  filterLibrary,
  loadLibrary,
} from "../recent/library";
import { CloseIcon, SearchIcon } from "../recent/parts";
import { SeriesCard, SeriesCardSkeleton } from "../recent/SeriesCard";
import { type SeriesActions, SeriesDetail } from "../recent/SeriesDetail";
import type { RestoredChat } from "./AskTab";

type ListState = { status: "loading" } | { status: "loaded"; library: Library } | { status: "error"; message: string };

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function RecentTab({
  onOpen,
  initialSeriesId = null,
}: {
  onOpen: (chat: RestoredChat) => void;
  /** Open this series' page straight away (from the Ask start screen). */
  initialSeriesId?: string | null;
}): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(initialSeriesId);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  /** `quiet` refreshes after a change without flashing the loading state. */
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setState({ status: "loading" });
    try {
      setState({ status: "loaded", library: await loadLibrary() });
    } catch (error) {
      setState({ status: "error", message: errorText(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const library = state.status === "loaded" ? state.library : null;
  const categories = useMemo(() => (library ? categoriesOf(library.series) : []), [library]);
  const visible = useMemo(
    () => (library ? filterLibrary(library.series, query, category) : []),
    [library, query, category]
  );
  const selected = library?.series.find((series) => series.id === selectedId) ?? null;
  const searching = query.trim() !== "";

  // A category can disappear (its last series renamed or deleted).
  useEffect(() => {
    if (category !== null && !categories.some((item) => item.name === category)) setCategory(null);
  }, [categories, category]);

  /** Runs one change, then refreshes the list from the server. */
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await work();
      await load(true);
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const openCapture = async (capture: LibraryCapture) => {
    setBusy(true);
    setActionError(null);
    try {
      if (capture.latestConversationId) {
        const detail = await getConversation(capture.latestConversationId);
        if (detail.slide) {
          onOpen({ conversationId: detail.id, slide: detail.slide, messages: detail.messages });
          return;
        }
      }
      onOpen({ conversationId: null, slide: await getSlide(capture.slideId), messages: [] });
    } catch (error) {
      setActionError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const signedIn = library?.signedIn ?? false;
  const actions: SeriesActions = {
    openCapture: (capture) => void openCapture(capture),
    deleteCapture: (capture) =>
      void run(async () => {
        if (signedIn) await deleteSlide(capture.slideId);
        await deleteCaptures([capture.slideId]).catch(() => undefined);
      }),
    deleteSeries: (series: LibrarySeries) => {
      const count = countLabel(series.captures.length, "slide");
      if (!window.confirm(`Delete "${series.title}" with its ${count} and their chats?`)) return;
      void run(async () => {
        const slideIds = series.captures.map((capture) => capture.slideId);
        if (signedIn && series.sorted) await deleteSeries(series.id);
        else if (signedIn) await Promise.all(slideIds.map((id) => deleteSlide(id)));
        await deleteCaptures(slideIds).catch(() => undefined);
        setSelectedId(null);
      });
    },
    rename: (series, title, category) => void run(() => updateSeries(series.id, { title, category })),
    setCover: (series, capture) => void run(() => updateSeries(series.id, { cover_slide_id: capture.slideId })),
    moveToSeries: (capture, seriesId) => void run(() => moveSlide(capture.slideId, { series_id: seriesId })),
    moveToNewSeries: (capture, title, category) => void run(() => moveSlide(capture.slideId, { title, category })),
  };

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const signIn = async () => {
    try {
      await signInWithGoogle();
      await load();
    } catch (error) {
      setState({ status: "error", message: errorText(error) });
    }
  };

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      {actionError && (
        <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          {actionError}
        </p>
      )}

      {selected && library ? (
        <SeriesDetail
          key={selected.id}
          series={selected}
          allSeries={library.series}
          busy={busy}
          actions={actions}
          onBack={() => setSelectedId(null)}
        />
      ) : (
        <>
          <h2 className="text-base font-semibold text-slate-800">Recent</h2>

          {state.status === "loading" && (
            <ul className="flex flex-col gap-3" aria-label="Loading your series">
              <SeriesCardSkeleton />
              <SeriesCardSkeleton />
              <SeriesCardSkeleton />
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

          {library && !library.signedIn && (
            <div className="flex flex-col items-start gap-3 rounded-md border border-slate-200 p-4 shadow-subtle">
              <p className="text-sm text-slate-600">
                Sign in to have your slides sorted by topic and kept across devices.
              </p>
              <Button onClick={() => void signIn()}>Sign in with Google</Button>
            </div>
          )}

          {library && library.series.length === 0 && (
            <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
              Nothing here yet. Capture a slide and it will be filed under its topic.
            </p>
          )}

          {library && library.series.length > 0 && (
            <>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
                  <SearchIcon />
                </span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search series and slides"
                  aria-label="Search series and slides"
                  className="w-full rounded-sm border border-slate-300 bg-white py-2 pl-9 pr-9 text-sm text-slate-800 transition-colors duration-[120ms] placeholder:text-slate-400 focus:border-indigo-400 [&::-webkit-search-cancel-button]:hidden"
                />
                {searching && (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    aria-label="Clear search"
                    className="absolute inset-y-0 right-1 my-auto flex h-7 w-7 items-center justify-center rounded-sm text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  >
                    <CloseIcon />
                  </button>
                )}
              </div>

              {categories.length > 1 && (
                <div
                  className="-mx-4 flex flex-none gap-2 overflow-x-auto px-4 py-0.5 [scrollbar-width:none]"
                  role="group"
                  aria-label="Categories"
                >
                  {[{ name: null as string | null, label: "All" }, ...categories.map((c) => ({ name: c.name, label: c.name }))].map(
                    ({ name, label }) => (
                      <button
                        key={label}
                        type="button"
                        aria-pressed={category === name}
                        onClick={() => setCategory(name)}
                        className={`flex-none rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-[120ms] ${
                          category === name
                            ? "border-indigo-600 bg-indigo-600 text-white"
                            : "border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {label}
                      </button>
                    )
                  )}
                </div>
              )}

              {visible.length === 0 ? (
                <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                  No series or slide matches "{query.trim()}".
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {visible.map((series) => (
                    <SeriesCard
                      key={series.id}
                      series={series}
                      // While searching, matches are shown without another click.
                      open={searching || expanded.has(series.id)}
                      busy={busy}
                      onToggle={() => toggle(series.id)}
                      onSelect={() => setSelectedId(series.id)}
                      onOpenCapture={(capture) => void openCapture(capture)}
                    />
                  ))}
                </ul>
              )}
            </>
          )}

          {library && (
            <p className="text-xs text-slate-400">
              Slides and chats are deleted {library.retentionDays} days after they were made. Pictures stay on this
              device only. You can delete anything sooner.
            </p>
          )}
        </>
      )}
    </div>
  );
}
