/**
 * One-time first-run welcome screen (shown once per install, tracked via
 * chrome.storage.local — see App.tsx). Offers Google sign-in up front
 * without gating anything on it: "Skip for now" and signing in both lead
 * to the same normal tab UI, since sign-in stays fully optional (Phase 2/3
 * — see SettingsTab.tsx's own note). Matches
 * VisionLearn_Premium_UI_Guide.md's "zero unnecessary popups" principle by
 * only ever appearing this once, not on every launch.
 */

import { useState } from "react";

import { signInWithGoogle } from "../shared/api-client";
import { Button } from "./components/Button";

type SignInState = { status: "idle" } | { status: "signing-in" } | { status: "error"; message: string };

export function WelcomeScreen({ onDone }: { onDone: () => void }): JSX.Element {
  const [signIn, setSignIn] = useState<SignInState>({ status: "idle" });

  const handleSignIn = async () => {
    setSignIn({ status: "signing-in" });
    try {
      await signInWithGoogle();
      onDone();
    } catch (error) {
      setSignIn({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center gap-6 bg-gradient-to-b from-indigo-50/60 to-white px-8 text-center">
      <img src="/icons/icon-128.png" alt="" className="h-16 w-16 rounded-md shadow-subtle" />

      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">Welcome to VisionLearn AI</h1>
        <p className="max-w-[280px] text-sm leading-relaxed text-slate-600">
          Capture any lecture slide and ask questions grounded in exactly what's on screen — equations, diagrams,
          and all.
        </p>
      </div>

      <div className="flex w-full max-w-[280px] flex-col gap-2">
        <Button onClick={() => void handleSignIn()} disabled={signIn.status === "signing-in"} className="w-full">
          {signIn.status === "signing-in" ? "Signing in…" : "Sign in with Google"}
        </Button>
        <button
          type="button"
          onClick={onDone}
          className="text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:text-slate-700"
        >
          Skip for now
        </button>
      </div>

      {signIn.status === "error" && <p className="max-w-[280px] text-xs text-red-600">{signIn.message}</p>}

      <p className="max-w-[280px] text-xs text-slate-400">
        Signing in is optional — everything works without it, and you can sign in later from Settings.
      </p>
    </div>
  );
}
