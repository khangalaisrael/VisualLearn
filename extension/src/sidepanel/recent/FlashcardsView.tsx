/**
 * Studying a deck of flashcards: read the front, recall, show the answer,
 * then say whether you had it. A card marked "Again" comes back at the end
 * of the round, so the round ends only when every card has been recalled.
 * Which cards are known is saved, so a deck can be picked up later.
 */

import { useCallback, useEffect, useState } from "react";

import type { StudyAidOut } from "@shared/types";

import { saveFlashcardProgress } from "../../shared/api-client";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { BackIcon } from "./parts";

export function FlashcardsView({ aid, onBack }: { aid: StudyAidOut; onBack: () => void }): JSX.Element {
  const cards = aid.cards ?? [];
  const [known, setKnown] = useState<number[]>(aid.known);
  // The cards still to recall this round, as positions in the deck; the first is on screen.
  const [queue, setQueue] = useState<number[]>(() => cards.map((_, i) => i).filter((i) => !aid.known.includes(i)));
  const [revealed, setRevealed] = useState(false);
  const resumed = aid.known.length > 0;

  const persist = useCallback(
    (next: number[]) => {
      // Best effort: studying carries on even if a save does not go through.
      void saveFlashcardProgress(aid.id, next).catch(() => undefined);
    },
    [aid.id]
  );

  const current = queue[0];

  const gotIt = useCallback(() => {
    if (current === undefined) return;
    const next = [...known, current].sort((a, b) => a - b);
    setKnown(next);
    persist(next);
    setQueue((rest) => rest.slice(1));
    setRevealed(false);
  }, [current, known, persist]);

  const again = useCallback(() => {
    setQueue((rest) => (rest.length > 1 ? [...rest.slice(1), rest[0]] : rest));
    setRevealed(false);
  }, []);

  const startOver = () => {
    setKnown([]);
    persist([]);
    setQueue(cards.map((_, i) => i));
    setRevealed(false);
  };

  // Space or Enter shows the answer; then 1 is Again and 2 is Got it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName ?? "";
      if (current === undefined || /^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
      // On a focused button, Space and Enter keep their usual meaning (press that button).
      if (!revealed && (event.key === " " || event.key === "Enter") && tag !== "BUTTON") {
        event.preventDefault();
        setRevealed(true);
      } else if (revealed && event.key === "1") {
        again();
      } else if (revealed && event.key === "2") {
        gotIt();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [revealed, current, again, gotIt]);

  const back = (
    <button
      type="button"
      onClick={onBack}
      className="-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700"
    >
      <BackIcon />
      Back to the series
    </button>
  );

  const progress = (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium tabular-nums text-slate-500" role="status">
        {known.length} of {cards.length} known
      </p>
      <div className="flex gap-0.5" aria-hidden="true">
        {cards.map((_, i) => (
          <span key={i} className={`h-1 flex-1 rounded-full ${known.includes(i) ? "bg-indigo-600" : "bg-slate-200"}`} />
        ))}
      </div>
    </div>
  );

  if (current === undefined) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <h2 className="text-lg font-semibold leading-snug text-slate-800">{aid.title}</h2>
        {progress}
        <p className="text-sm text-slate-600">
          You recalled every card. Come back to them in a day or two: recalling again after a gap is what makes it
          stick.
        </p>
        <div className="flex gap-2">
          <Button onClick={startOver}>Go through them again</Button>
          <Button variant="secondary" onClick={onBack}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  const card = cards[current];
  return (
    <div className="flex flex-col gap-4">
      {back}
      <h2 className="text-lg font-semibold leading-snug text-slate-800">{aid.title}</h2>
      {progress}

      <div className="flex min-h-[220px] flex-col rounded-md border border-slate-200 bg-white shadow-subtle">
        <div className="flex flex-1 flex-col justify-center overflow-x-auto p-4 text-base font-medium leading-relaxed text-slate-800">
          <MathText text={card.front} />
        </div>
        {revealed && (
          <div className="overflow-x-auto border-t border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
            <MathText text={card.back} />
          </div>
        )}
      </div>

      {revealed ? (
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" onClick={again}>
            Again
          </Button>
          <Button onClick={gotIt}>Got it</Button>
        </div>
      ) : (
        <Button onClick={() => setRevealed(true)} className="w-full">
          Show answer
        </Button>
      )}

      <p className="text-xs tabular-nums text-slate-400">
        {queue.length} left this round{resumed && known.length === aid.known.length ? ", picking up where you left off" : ""}.
        Say the answer to yourself before you look.
      </p>
      <p className="text-xs text-slate-400">Keys: Space shows the answer, then 1 for Again or 2 for Got it.</p>
    </div>
  );
}
