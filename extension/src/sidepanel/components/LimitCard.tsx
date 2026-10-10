/**
 * Friendly stand-in for the old red error box when a usage limit stops a
 * capture. Calm muted purple, plain language, a live countdown, and — for
 * the person's own limits — a way to say they'd want more (the Pro
 * waitlist). The global capacity card has no waitlist: it isn't about them.
 */

import { useEffect, useState } from "react";

import { joinProWaitlist, signInWithGoogle } from "../../shared/api-client";
import { type ActiveLimit, refreshUsage, useUsage } from "../../shared/usage-store";
import { Button } from "./Button";

export function formatCountdown(ms: number): string {
  const totalMinutes = Math.max(0, Math.ceil(ms / 60_000));
  if (totalMinutes < 1) return "less than a minute";
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

function useCountdown(target: Date): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);
  return formatCountdown(target.getTime() - now);
}

type WaitlistState = "idle" | "working" | "joined" | "error";

function WaitlistPrompt({ source }: { source: "daily" | "monthly" }): JSX.Element {
  const usage = useUsage();
  const [state, setState] = useState<WaitlistState>("idle");

  const join = async () => {
    setState("working");
    try {
      // Signed-out visitors sign in first: the whole point is being able to
      // email the people who'd want more.
      if (!usage?.signed_in) {
        await signInWithGoogle();
        await refreshUsage();
      }
      await joinProWaitlist(source);
      setState("joined");
    } catch {
      setState("error");
    }
  };

  if (state === "joined") {
    return <p className="text-sm text-violet-700">You're on the list — we'll email you when Pro is ready.</p>;
  }
  return (
    <div className="flex flex-col items-start gap-2 border-t border-violet-100 pt-3">
      <p className="text-sm text-slate-600">Want more?</p>
      <Button variant="secondary" disabled={state === "working"} onClick={() => void join()} className="text-xs">
        {state === "working"
          ? "Joining…"
          : usage?.signed_in
            ? "Join the Pro waitlist"
            : "Sign in to join the Pro waitlist"}
      </Button>
      {state === "error" && <p className="text-xs text-slate-500">That didn't work — please try again.</p>}
    </div>
  );
}

export function LimitCard({ limit }: { limit: ActiveLimit }): JSX.Element {
  const countdown = useCountdown(limit.resetsAt);

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-violet-100 bg-violet-50/50 p-4 shadow-subtle">
      {limit.kind === "daily" && (
        <>
          <h3 className="text-base font-semibold text-slate-800">You're done for today</h3>
          <p className="text-sm text-slate-600">
            You captured {limit.used} slides. Your limit resets at midnight — in{" "}
            <span className="font-medium tabular-nums text-slate-800">{countdown}</span>.
          </p>
        </>
      )}
      {limit.kind === "monthly" && (
        <>
          <h3 className="text-base font-semibold text-slate-800">You've used this month's captures</h3>
          <p className="text-sm text-slate-600">
            You've used {limit.used} captures this month. Your allowance resets on the 1st.
          </p>
        </>
      )}
      {limit.kind === "global" && (
        <>
          <h3 className="text-base font-semibold text-slate-800">We've hit today's capacity</h3>
          <p className="text-sm text-slate-600">
            We're a small student project and keep costs low. Back tomorrow!
          </p>
        </>
      )}
      {limit.kind !== "global" && <WaitlistPrompt source={limit.kind} />}
    </section>
  );
}
