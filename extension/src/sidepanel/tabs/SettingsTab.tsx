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
  deleteAccount,
  getAuthState,
  getConfig,
  getPrivacyPolicyUrl,
  signInWithGoogle,
  signInWithGooglePicker,
  signOut,
} from "../../shared/api-client";
import { clearCaptures } from "../../shared/capture-store";
import { type ThemeChoice, getTheme, setTheme } from "../../shared/theme";
import { refreshUsage, useUsage } from "../../shared/usage-store";
import { Button } from "../components/Button";

type ConnectionState = { status: "checking" } | { status: "ok" } | { status: "error" };

type SignInState =
  | { status: "signed-out" }
  | { status: "signing-in" }
  | { status: "signed-in"; email: string | null }
  | { status: "error"; message: string };

export function SettingsTab(): JSX.Element {
  const usage = useUsage();
  const [theme, setThemeChoice] = useState<ThemeChoice>("system");
  useEffect(() => {
    void getTheme().then(setThemeChoice);
  }, []);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [policyUrl, setPolicyUrl] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>({ status: "checking" });
  const [signIn, setSignIn] = useState<SignInState>({ status: "signed-out" });

  useEffect(() => {
    getPrivacyPolicyUrl().then(setPolicyUrl);
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
      void refreshUsage();
    } catch (error) {
      setSignIn({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  const handleSignOut = async () => {
    await signOut();
    setSignIn({ status: "signed-out" });
    void refreshUsage();
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
      // The thumbnails and text kept in this browser go with the account.
      await clearCaptures().catch(() => undefined);
      setConfirmingDelete(false);
      setSignIn({ status: "signed-out" });
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleSwitchAccount = async () => {
    setSignIn({ status: "signing-in" });
    try {
      const auth = await signInWithGooglePicker();
      setSignIn({ status: "signed-in", email: auth.email });
      void refreshUsage();
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
              <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
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
            {confirmingDelete ? (
              <div className="flex flex-col gap-2 rounded-md bg-red-50 p-3">
                <p className="text-xs text-red-800 dark:text-red-200">
                  This permanently deletes your account, all your chats and your captured slides. It can't be undone.
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={deleting}
                    onClick={() => void handleDeleteAccount()}
                    className="rounded-sm bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors duration-[120ms] hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleting ? "Deleting…" : "Yes, delete everything"}
                  </button>
                  <Button variant="secondary" onClick={() => setConfirmingDelete(false)} className="text-xs">
                    Cancel
                  </Button>
                </div>
                {deleteError && <p className="text-xs text-red-700 dark:text-red-300">{deleteError}</p>}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                className="self-start text-xs font-medium text-slate-400 transition-colors duration-[120ms] hover:text-red-600 dark:hover:text-red-400"
              >
                Delete my account and data
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Button onClick={() => void handleSignIn()} disabled={signIn.status === "signing-in"}>
              {signIn.status === "signing-in" ? "Signing in…" : "Sign in with Google"}
            </Button>
            {signIn.status === "error" && <p className="text-xs text-red-600 dark:text-red-400">{signIn.message}</p>}
            <p className="text-xs text-slate-400">Optional — everything works without signing in.</p>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
        <h2 className="text-sm font-semibold text-slate-800">Appearance</h2>
        <div role="group" aria-label="Theme" className="flex gap-1 rounded-md bg-slate-100 p-1">
          {(["system", "light", "dark"] as const).map((choice) => (
            <button
              key={choice}
              type="button"
              aria-pressed={theme === choice}
              onClick={() => {
                setThemeChoice(choice);
                void setTheme(choice);
              }}
              className={`flex-1 rounded-sm px-3 py-1.5 text-xs font-medium capitalize transition-colors duration-[120ms] ${
                theme === choice
                  ? "bg-white text-slate-800 shadow-subtle"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {choice}
            </button>
          ))}
        </div>
      </section>

      {usage?.is_admin && (
        <section className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-subtle">
          <h2 className="text-sm font-semibold text-slate-800">Admin</h2>
          <p className="text-xs text-slate-500">Spend, usage per user, outliers and Pro waitlist demand.</p>
          <Button
            variant="secondary"
            onClick={() => void chrome.runtime.openOptionsPage()}
            className="self-start text-xs"
          >
            Open admin dashboard
          </Button>
        </section>
      )}

      {policyUrl && (
        <a
          href={policyUrl}
          target="_blank"
          rel="noreferrer"
          className="px-1 text-xs font-medium text-indigo-600 dark:text-indigo-300 underline-offset-2 hover:underline"
        >
          Privacy policy
        </a>
      )}

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
