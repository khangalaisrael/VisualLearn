/**
 * One series in the list, like a playlist: its name opens the series page;
 * the arrow unfolds its slides in place. The header carries no picture, only
 * the slides under it do.
 */

import { type LibraryCapture, type LibrarySeries, countLabel, relativeTime } from "./library";
import { ChevronIcon, ICON_BUTTON, SlideRow } from "./parts";

export function SeriesCard({
  series,
  open,
  busy,
  onToggle,
  onSelect,
  onOpenCapture,
}: {
  series: LibrarySeries;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onSelect: () => void;
  onOpenCapture: (capture: LibraryCapture) => void;
}): JSX.Element {
  const practice = series.captures.filter((capture) => capture.kind === "practice").length;
  const listId = `series-captures-${series.id}`;
  return (
    <li className="rounded-md border border-slate-200 bg-white shadow-subtle">
      <div className="flex items-center gap-1 p-2">
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-sm px-2 py-1.5 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
        >
          <span className="line-clamp-2 text-sm font-semibold leading-snug text-slate-800">{series.title}</span>
          <span className="truncate text-xs text-slate-500">{series.category}</span>
          <span className="text-xs text-slate-400">
            {countLabel(series.captures.length, "slide")}
            {practice > 0 && `, ${practice} practice`}, {relativeTime(series.lastActivity).toLowerCase()}
          </span>
        </button>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={listId}
          aria-label={`${open ? "Hide" : "Show"} the slides in ${series.title}`}
          className={ICON_BUTTON}
        >
          <ChevronIcon open={open} />
        </button>
      </div>

      {open && (
        <ul id={listId} className="flex flex-col border-t border-slate-100 p-1">
          {series.captures.map((capture) => (
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
