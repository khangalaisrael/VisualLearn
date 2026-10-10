/**
 * Shown instead of the capture area when the server is invite-only and this
 * visitor isn't on the list: signed out (ask them to sign in), or signed in
 * with an account that wasn't invited (say which, and offer another account).
 */

import { useState } from "react";

import { getAuthState, signInWithGoogle, signInWithGooglePicker } from "../../shared/api-client";
import { refreshUsage, useUsage } from "../../shared/usage-store";
import { Button } from "./Button";

export function isBlockedByInvite(usage: ReturnType<typeof useUsage>): boolean {
  return Boolean(usage && usage.invite_only && !usage.allowed);
}

export function InviteOnlyCard(): JSX.Element {
  const usage = useUsage();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<unknown>) => {
    setWorking(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      // A refused sign-in explains itself ("invite-only right now…").
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      await refreshUsage();
      setWorking(false);
    }
  };

  const signedIn = Boolean(usage?.signed_in);
  const contact = usage?.invite_contact;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-violet-100 bg-violet-50/50 p-4 shadow-subtle">
      <h3 className="text-base font-semibold text-slate-800">VisionLearn is invite-only right now</h3>
      <p className="text-sm text-slate-600">
        {signedIn
          ? "The account you're signed in with isn't on the invite list. Try the Google account you were invited with."
          : "Sign in with the Google account you were invited with to start capturing."}
      </p>
      <div className="flex items-center gap-2">
        <Button
          disabled={working}
          onClick={() => void run(async () => (signedIn ? signInWithGooglePicker() : signInWithGoogle()))}
          className="text-xs"
        >
          {working ? "Signing in…" : signedIn ? "Use a different account" : "Sign in with Google"}
        </Button>
      </div>
      {error && <p className="text-xs text-slate-600">{error}</p>}
      <p className="border-t border-violet-100 pt-3 text-xs text-slate-500">
        Not invited yet? {contact ? <>Email <span className="font-medium">{contact}</span> with your Gmail address.</> : "Ask for an invite."}
      </p>
    </section>
  );
}

// Re-exported so callers can refresh after a manual account change.
export { getAuthState };
