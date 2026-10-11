/** Small pieces shared by the series list and the series page. */

import { useEffect, useMemo } from "react";

import { type LibraryCapture, relativeTime } from "./library";

const ICON = "h-4 w-4";
const STROKE = { stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function SearchIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={ICON} aria-hidden="true">
      <circle cx="9" cy="9" r="5.25" {...STROKE} />
      <path d="m13 13 3.5 3.5" {...STROKE} />
    </svg>
  );
}

export function ChevronIcon({ open }: { open: boolean }): JSX.Element {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      className={`${ICON} transition-transform duration-[120ms] ${open ? "rotate-180" : ""}`}
      aria-hidden="true"
    >
      <path d="m5.5 8 4.5 4.5L14.5 8" {...STROKE} />
    </svg>
  );
}

export function BackIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={ICON} aria-hidden="true">
      <path d="M12 5.5 7.5 10l4.5 4.5" {...STROKE} />
    </svg>
  );
}

/** Points onward: pressing this row opens something. */
export function ForwardIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={ICON} aria-hidden="true">
      <path d="M8 5.5 12.5 10 8 14.5" {...STROKE} />
    </svg>
  );
}

/** A star: solid when the thing is a favourite, an outline when it is not. */
export function StarIcon({ filled }: { filled: boolean }): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill={filled ? "currentColor" : "none"} className={ICON} aria-hidden="true">
      <path
        d="m10 2.75 2.2 4.6 5.05.66-3.7 3.5.95 5-4.5-2.47-4.5 2.47.95-5-3.7-3.5 5.05-.66L10 2.75Z"
        {...STROKE}
      />
    </svg>
  );
}

export function MoreIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={ICON} aria-hidden="true">
      <circle cx="4.5" cy="10" r="1.4" />
      <circle cx="10" cy="10" r="1.4" />
      <circle cx="15.5" cy="10" r="1.4" />
    </svg>
  );
}

export function CloseIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={ICON} aria-hidden="true">
      <path d="m6 6 8 8M14 6l-8 8" {...STROKE} />
    </svg>
  );
}

/** A reply arrow: marks a suggested follow-up question. */
export function FollowUpIcon(): JSX.Element {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5 flex-none" aria-hidden="true">
      <path d="M5 4.5v4a3 3 0 0 0 3 3h7M11.5 8l3.5 3.5-3.5 3.5" {...STROKE} />
    </svg>
  );
}

/** Square icon button used for row actions. */
export const ICON_BUTTON =
  "flex h-8 w-8 flex-none items-center justify-center rounded-sm text-slate-400 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50";

/**
 * A 16:9 picture: the capture's thumbnail when this device has it, otherwise
 * the title set in type, so a series synced from another device still has a
 * recognisable cover instead of an empty box.
 */
export function Cover({
  blob,
  title,
  className = "",
  small = false,
}: {
  blob: Blob | null;
  title: string;
  className?: string;
  /** Too small to set the title in: without a picture it is a plain tinted block. */
  small?: boolean;
}): JSX.Element {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  const frame = `aspect-video flex-none overflow-hidden border border-slate-200 ${small ? "rounded" : "rounded-sm"} ${className}`;
  return url ? (
    <img src={url} alt="" className={`${frame} object-cover`} />
  ) : (
    <div className={`${frame} flex items-center bg-slate-100 ${small ? "" : "p-2"}`} aria-hidden="true">
      {!small && <span className="line-clamp-2 text-[11px] font-semibold leading-tight text-slate-500">{title}</span>}
    </div>
  );
}

export function PracticeTag(): JSX.Element {
  return (
    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:text-amber-300">
      Practice
    </span>
  );
}

/**
 * One slide of a series as a playlist row: its number, a small picture, a
 * one-line title and one line of detail. The whole row opens the slide.
 */
export function SlideRow({
  capture,
  disabled,
  onOpen,
}: {
  capture: LibraryCapture;
  disabled: boolean;
  onOpen: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onOpen}
      className="flex min-w-0 flex-1 items-center gap-2.5 rounded-sm px-1.5 py-1.5 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100 disabled:opacity-50"
    >
      <span className="w-5 flex-none text-center text-xs tabular-nums text-slate-400">{capture.position}</span>
      {capture.thumbnail && <Cover blob={capture.thumbnail} title="" className="w-14" small />}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium text-slate-800">
          {capture.subtopic ?? (capture.summary || "Captured slide")}
        </span>
        <span className="flex items-center gap-2 text-xs text-slate-400">
          <span className="truncate">{relativeTime(capture.capturedAt)}</span>
          {capture.kind === "practice" && <PracticeTag />}
          {capture.followUps > 0 && (
            <span className="flex-none text-indigo-600 dark:text-indigo-300">
              {capture.followUps} {capture.followUps === 1 ? "follow-up" : "follow-ups"}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
