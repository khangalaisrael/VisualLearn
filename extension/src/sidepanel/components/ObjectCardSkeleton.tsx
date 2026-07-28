/**
 * Loading placeholder shaped like ObjectCard, shown while a capture is
 * being analyzed — a plain "Analyzing…" string doesn't tell the user
 * what's about to appear (Premium UI Guide: "Loading states everywhere").
 */
export function ObjectCardSkeleton(): JSX.Element {
  return (
    <li className="flex animate-pulse flex-col gap-2 rounded-md bg-white p-4 shadow-subtle">
      <div className="h-4 w-16 rounded-full bg-slate-200" />
      <div className="h-4 w-3/4 rounded-sm bg-slate-100" />
      <div className="h-4 w-1/2 rounded-sm bg-slate-100" />
    </li>
  );
}
