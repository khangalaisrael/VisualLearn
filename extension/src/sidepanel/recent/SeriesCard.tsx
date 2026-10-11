/**
 * One series in the list. Pressing it opens the series page, where its
 * slides, quizzes and study aids are. Nothing unfolds in place. Only a search
 * that matched particular slides lists those slides under the series, each
 * pressable on its own.
 */

import { type LibraryCapture, type SeriesHit, countLabel, relativeTime } from "./library";
import { ForwardIcon, SlideRow } from "./parts";

export function SeriesCard({
  hit,
  busy,
  onSelect,
  onOpenCapture,
}: {
  hit: SeriesHit;
  busy: boolean;
  onSelect: () => void;
  onOpenCapture: (capture: LibraryCapture) => void;
}): JSX.Element {
  const { series, slideMatches } = hit;
  const practice = series.captures.filter((capture) => capture.kind === "practice").length;
  return (
    <li className="rounded-md border border-slate-200 bg-white shadow-subtle">
      <button
        type="button"
        onClick={onSelect}
        className="flex w-full items-center gap-3 rounded-md px-4 py-3 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="line-clamp-2 text-sm font-semibold leading-snug text-slate-800">{series.title}</span>
          <span className="truncate text-xs text-slate-500">{series.category}</span>
          <span className="text-xs text-slate-400">
            {countLabel(series.captures.length, "slide")}
            {practice > 0 && `, ${practice} practice`}, {relativeTime(series.lastActivity).toLowerCase()}
          </span>
        </span>
        <span className="flex-none text-slate-400">
          <ForwardIcon />
        </span>
      </button>

      {slideMatches && (
        <ul className="flex flex-col border-t border-slate-100 p-1" aria-label={`Matching slides in ${series.title}`}>
          {slideMatches.map((capture) => (
            <li key={capture.slideId} className="flex">
              <SlideRow capture={capture} disabled={busy} onOpen={() => onOpenCapture(capture)} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function SeriesCardSkeleton(): JSX.Element {
  return (
    <li className="flex animate-pulse flex-col gap-2 rounded-md border border-slate-200 p-4" aria-hidden="true">
      <span className="h-3 w-2/3 rounded bg-slate-100" />
      <span className="h-3 w-1/2 rounded bg-slate-100" />
      <span className="h-3 w-1/3 rounded bg-slate-100" />
    </li>
  );
}
