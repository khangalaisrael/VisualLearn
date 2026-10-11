/**
 * What the Ask view shows before a slide is captured. Someone who has
 * studied here before gets their most recent series to pick up again; someone
 * new gets the three steps. Either way the capture shortcut is shown as it is
 * actually bound, since it can be changed at chrome://extensions/shortcuts.
 */

import { useEffect, useState } from "react";

import { type LibrarySeries, countLabel, coverOf, loadLibrary, relativeTime } from "../recent/library";
import { Cover } from "../recent/parts";

const SERIES_SHOWN = 3;
const STEPS = ["Open a lecture slide in this tab", "Press Capture", "Ask anything about what's on it"];

type RecentState = { status: "loading" } | { status: "loaded"; series: LibrarySeries[] };

function useCaptureShortcut(): string {
  const [shortcut, setShortcut] = useState("");
  useEffect(() => {
    chrome.commands
      .getAll()
      .then((commands) => setShortcut(commands.find((command) => command.name === "capture-slide")?.shortcut ?? ""))
      .catch(() => undefined);
  }, []);
  return shortcut;
}

export function StartScreen({
  active,
  onOpenSeries,
}: {
  /** The Ask view is on screen: the list is refreshed each time it comes back. */
  active: boolean;
  onOpenSeries: (seriesId: string) => void;
}): JSX.Element {
  const [recent, setRecent] = useState<RecentState>({ status: "loading" });
  const shortcut = useCaptureShortcut();

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const load = () =>
      loadLibrary()
        .then((library) => !cancelled && setRecent({ status: "loaded", series: library.series.slice(0, SERIES_SHOWN) }))
        // Offline, or the server is waking: the steps below still make sense.
        .catch(() => !cancelled && setRecent({ status: "loaded", series: [] }));
    void load();
    // Signing in or out changes whose series these are.
    const onChange = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "local" && changes.sessionToken) void load();
    };
    chrome.storage.onChanged.addListener(onChange);
    return () => {
      cancelled = true;
      chrome.storage.onChanged.removeListener(onChange);
    };
  }, [active]);

  const shortcutHint = shortcut && (
    <p className="text-xs text-slate-400">
      Capture from the keyboard with{" "}
      <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
        {shortcut}
      </kbd>
    </p>
  );

  if (recent.status === "loading") {
    return (
      <ul className="flex animate-pulse flex-col gap-2" aria-hidden="true">
        {[0, 1].map((row) => (
          <li key={row} className="flex items-center gap-3 rounded-md border border-slate-200 p-3">
            <span className="aspect-video w-16 flex-none rounded-sm bg-slate-100" />
            <span className="flex flex-1 flex-col gap-2">
              <span className="h-3 w-2/3 rounded bg-slate-100" />
              <span className="h-3 w-1/3 rounded bg-slate-100" />
            </span>
          </li>
        ))}
      </ul>
    );
  }

  if (recent.series.length > 0) {
    return (
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-slate-800">Pick up where you left off</h3>
        <ul className="flex flex-col gap-2">
          {recent.series.map((series) => (
            <li key={series.id}>
              <button
                type="button"
                onClick={() => onOpenSeries(series.id)}
                className="flex w-full items-center gap-3 rounded-md border border-slate-200 bg-white p-3 text-left shadow-subtle transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
              >
                <Cover blob={coverOf(series)} title={series.title} className="w-16" />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-sm font-semibold text-slate-800">{series.title}</span>
                  <span className="truncate text-xs text-slate-500">{series.category}</span>
                  <span className="text-xs text-slate-400">
                    {countLabel(series.captures.length, "slide")}, {relativeTime(series.lastActivity).toLowerCase()}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="text-sm text-slate-500">Or open a new slide in this tab and press Capture.</p>
        {shortcutHint}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-5 px-4 py-8 text-center">
      <img src="/icons/icon-128.png" alt="" className="h-14 w-14 rounded-md shadow-subtle" />
      <div className="flex flex-col gap-1">
        <p className="text-base font-semibold text-slate-800">Understand any slide</p>
        <p className="text-sm text-slate-500">Equations, diagrams and code, explained from what's on screen.</p>
      </div>
      <ol className="flex w-full max-w-[280px] flex-col gap-2 text-left">
        {STEPS.map((step, index) => (
          <li key={step} className="flex items-center gap-3 rounded-md bg-slate-50 px-3 py-2.5 text-sm text-slate-600">
            <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold tabular-nums text-indigo-700 dark:text-indigo-300">
              {index + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      {shortcutHint}
    </div>
  );
}

/** Shown once to people who used VisionLearn before 2.0; new users get the welcome screen instead. */
export function WhatsNewCard({ onOpenRecent, onDismiss }: { onOpenRecent: () => void; onDismiss: () => void }): JSX.Element {
  return (
    <section className="flex flex-col gap-3 rounded-md border border-indigo-200 bg-indigo-50/50 p-4" aria-label="New in VisionLearn 2.0">
      <h3 className="text-sm font-semibold text-slate-800">New in VisionLearn 2.0</h3>
      <ul className="flex flex-col gap-1.5 text-sm text-slate-600">
        <li>Your slides are sorted into series by topic, and you can search them.</li>
        <li>Each series can quiz you, with a tutor for the questions you miss.</li>
        <li>It can also write you a study guide, a cheat sheet and flashcards.</li>
        <li>Answers can be saved as notes that you edit and keep.</li>
        <li>The chat carries on when you capture the next slide of a topic.</li>
        <li>The Chat tab is for questions that are not about a slide.</li>
      </ul>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onOpenRecent}
          className="rounded-sm bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors duration-[120ms] hover:bg-indigo-700 active:bg-indigo-800"
        >
          See your series
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-sm px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors duration-[120ms] hover:bg-indigo-100"
        >
          Got it
        </button>
      </div>
    </section>
  );
}
