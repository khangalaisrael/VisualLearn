/**
 * The quiet "12/20" counter in the panel corner: a small ring and the
 * numbers, nothing louder. Indigo while there's plenty left, amber from
 * three quarters used (15/20), and a calm muted purple (not red) once the
 * limit is reached — hitting a limit is normal, not an error.
 */

import { useUsage } from "../../shared/usage-store";

const RADIUS = 8;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function tone(used: number, limit: number): { stroke: string; text: string } {
  const share = limit > 0 ? used / limit : 1;
  if (share >= 1) return { stroke: "stroke-violet-300", text: "text-violet-500 dark:text-violet-300" };
  if (share >= 0.75) return { stroke: "stroke-amber-400", text: "text-amber-600 dark:text-amber-400" };
  return { stroke: "stroke-indigo-400", text: "text-slate-500" };
}

export function UsageMeter(): JSX.Element | null {
  const usage = useUsage();
  if (!usage) return null;

  if (usage.unlimited) {
    return <span className="px-1 text-xs font-medium text-slate-400">Unlimited</span>;
  }

  const { used, limit } = usage.captures_today;
  const shown = Math.min(used, limit);
  const { stroke, text } = tone(used, limit);
  const filled = limit > 0 ? (shown / limit) * CIRCUMFERENCE : 0;

  return (
    <div
      className="flex items-center gap-1.5 px-1"
      title={`${shown} of ${limit} captures used today`}
      role="img"
      aria-label={`${shown} of ${limit} captures used today`}
    >
      <svg viewBox="0 0 20 20" className="h-[18px] w-[18px] -rotate-90" aria-hidden="true">
        <circle cx="10" cy="10" r={RADIUS} fill="none" strokeWidth="2.5" className="stroke-slate-100" />
        <circle
          cx="10"
          cy="10"
          r={RADIUS}
          fill="none"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
          className={`${stroke} transition-[stroke-dasharray] duration-[180ms]`}
        />
      </svg>
      <span className={`text-xs font-medium tabular-nums ${text}`}>
        {shown}/{limit}
      </span>
    </div>
  );
}
