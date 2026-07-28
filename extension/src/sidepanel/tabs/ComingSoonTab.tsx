/**
 * Placeholder for tabs not yet implemented (docs/ROADMAP.md, Milestone 2:
 * "tab shells (non-functional except Ask)"). Reused by Concepts/Notes/Quiz
 * in App.tsx rather than duplicating the same empty-state markup three
 * times — per the Premium UI Guide, every empty state should still name a
 * next action, so this points the user back at the one tab that works.
 */

interface ComingSoonTabProps {
  tabName: string;
  milestone: string;
}

export function ComingSoonTab({ tabName, milestone }: ComingSoonTabProps): JSX.Element {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
      <p className="text-sm font-medium tracking-tight text-slate-700">{tabName} isn't built yet</p>
      <p className="max-w-[26em] text-sm text-slate-500">
        This tab lands in {milestone}. For now, use the Ask tab to capture and inspect slides.
      </p>
    </div>
  );
}
