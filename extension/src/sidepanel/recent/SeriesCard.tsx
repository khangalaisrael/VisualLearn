/**
 * One series in the list. Pressing it opens the series page, where its
 * slides, quizzes and study aids are. Nothing unfolds in place. Only a search
 * that matched particular slides lists those slides under the series, each
 * pressable on its own. The star marks a favourite; favourites come first.
 */

import { type LibraryCapture, type SeriesHit, countLabel, relativeTime } from "./library";
import { ForwardIcon, SlideRow, StarIcon } from "./parts";

// The star sets its own colour (amber when on), so it does not reuse the grey icon-button style.
const STAR_BUTTON =
  "flex h-8 w-8 flex-none items-center justify-center rounded-sm transition-colors duration-[120ms] hover:bg-slate-100 disabled:opacity-50";

export function SeriesCard({
  hit,
  busy,
  onSelect,
  onToggleStar,
  onOpenCapture,
}: {
  hit: SeriesHit;
  busy: boolean;
  onSelect: () => void;
  onToggleStar: () => void;
  onOpenCapture: (capture: LibraryCapture) => void;
}): JSX.Element {
  const { series, slideMatches } = hit;
  const practice = series.captures.filter((capture) => capture.kind === "practice").length;
  return (
    <li className="rounded-md border border-slate-200 bg-white shadow-subtle">
      <div className="flex items-center gap-1 pr-2">
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-3 rounded-md py-3 pl-4 pr-2 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
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
        {/* Only a series kept on the server can be a favourite. */}
        {series.sorted && (
          <button
            type="button"
            disabled={busy}
            onClick={onToggleStar}
            aria-pressed={series.starred}
            aria-label={series.starred ? `Remove ${series.title} from favourites` : `Add ${series.title} to favourites`}
            title={series.starred ? "Remove from favourites" : "Add to favourites"}
            className={`${STAR_BUTTON} ${
              series.starred ? "text-amber-600 dark:text-amber-300" : "text-slate-400 hover:text-slate-700"
            }`}
          >
            <StarIcon filled={series.starred} />
          </button>
        )}
      </div>

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
