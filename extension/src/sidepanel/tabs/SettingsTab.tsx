/**
 * Settings tab — user-facing account controls only. Backend URL, API key,
 * and model selection are all baked in at build time (shared/api-client.ts
 * — VITE_BACKEND_URL / VITE_LOCAL_API_KEY) and deliberately not exposed
 * here: a real distributed user shouldn't be able to point the extension
 * at an arbitrary backend or hand-edit a credential. Connection health is
 * checked automatically on mount rather than behind a manual button, for
 * the same reason — nothing here asks the user to debug anything.
 */

import { useEffect, useState } from "react";

import {
  checkHealth,
  getAuthState,
  getConfig,
  signInWithGoogle,
  signInWithGooglePicker,
  signOut,
} from "../../shared/api-client";
import { Button } from "../components/Button";

type ConnectionState = { status: "checking" } | { status: "ok" } | { status: "error" };

type SignInState =
  | { status: "signed-out" }
  | { status: "signing-in" }
  | { status: "signed-in"; email: string | null }
  | { status: "error"; message: string };

export function SettingsTab(): JSX.Element {
  const [connection, setConnection] = useState<ConnectionState>({ status: "checking" });
  const [signIn, setSignIn] = useState<SignInState>({ status: "signed-out" });

  useEffect(() => {
    getConfig().then(({ backendUrl }) => {
      checkHealth(backendUrl)
        .then(() => setConnection({ status: "ok" }))
        .catch(() => setConnection({ status: "error" }));
    });
    getAuthState().then((auth) => {
      if (auth.sessionToken) {
        setSignIn({ status: "signed-in", email: auth.email });
      }
    });
  }, []);

  const handleSignIn = async () => {
    setSignIn({ status: "signing-in" });
    try {
      const auth = await signInWithGoogle();
      setSignIn({ status: "signed-in", email: auth.email });
    } catch (error) {
      setSignIn({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  const handleSignOut = async () => {
    await signOut();
    setSignIn({ status: "signed-out" });
  };

  const handleSwitchAccount = async () => {
    setSignIn({ status: "signing-in" });
    try {
      const auth = await signInWithGooglePicker();
      setSignIn({ status: "signed-in", email: auth.email });
    } catch (error) {
      setSignIn({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-5 overflow-y-auto p-5">
      <section className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
        <h2 className="text-sm font-semibold text-slate-800">Account</h2>

        {signIn.status === "signed-in" ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
                {(signIn.email ?? "?").charAt(0).toUpperCase()}
              </span>
              <span className="text-sm text-slate-700">{signIn.email ?? "Signed in"}</span>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => void handleSwitchAccount()} className="text-xs">
                Switch account
              </Button>
              <Button variant="secondary" onClick={() => void handleSignOut()} className="text-xs">
                Sign out
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Button onClick={() => void handleSignIn()} disabled={signIn.status === "signing-in"}>
              {signIn.status === "signing-in" ? "Signing in…" : "Sign in with Google"}
            </Button>
            {signIn.status === "error" && <p className="text-xs text-red-600">{signIn.message}</p>}
            <p className="text-xs text-slate-400">Optional — everything works without signing in.</p>
          </div>
        )}
      </section>

      <div className="flex items-center gap-2 px-1 text-xs text-slate-400">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            connection.status === "ok"
              ? "bg-emerald-500"
              : connection.status === "error"
                ? "bg-red-500"
                : "animate-pulse bg-slate-300"
          }`}
        />
        {connection.status === "ok" && "Connected"}
        {connection.status === "checking" && "Checking connection…"}
        {connection.status === "error" && "Can't reach the server right now — try again shortly."}
      </div>
    </div>
  );
}
