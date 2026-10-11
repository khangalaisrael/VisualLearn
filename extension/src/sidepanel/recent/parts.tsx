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
export function Cover({ blob, title, className = "" }: { blob: Blob | null; title: string; className?: string }): JSX.Element {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  const frame = `aspect-video flex-none overflow-hidden rounded-sm border border-slate-200 ${className}`;
  return url ? (
    <img src={url} alt="" className={`${frame} object-cover`} />
  ) : (
    <div className={`${frame} flex items-center bg-slate-100 p-2`} aria-hidden="true">
      <span className="line-clamp-2 text-[11px] font-semibold leading-tight text-slate-500">{title}</span>
    </div>
  );
}

export function PracticeTag(): JSX.Element {
  return (
    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:text-amber-200">
      Practice
    </span>
  );
}

/** One capture: picture, what it covers, when. The whole row opens it. */
export function CaptureButton({
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
      className="flex min-w-0 flex-1 gap-3 rounded-sm p-2 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100 disabled:opacity-50"
    >
      <Cover blob={capture.thumbnail} title={capture.subtopic ?? capture.pageTitle} className="w-[72px]" />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        {capture.subtopic && <span className="truncate text-sm font-medium text-slate-800">{capture.subtopic}</span>}
        <span className={`text-slate-600 ${capture.subtopic ? "line-clamp-1 text-xs" : "line-clamp-2 text-sm"}`}>
          {capture.summary || "Captured slide"}
        </span>
        <span className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          {relativeTime(capture.capturedAt)}
          {capture.kind === "practice" && <PracticeTag />}
          {capture.followUps > 0 && (
            <span className="text-indigo-600 dark:text-indigo-300">
              {capture.followUps} {capture.followUps === 1 ? "follow-up" : "follow-ups"}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
