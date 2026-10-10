/**
 * Recent chats for the signed-in account. History lives on the server, so
 * it follows the account across devices; signed-out users are offered
 * sign-in instead of a list. How long chats are kept comes from the
 * server, never hardcoded here.
 */

import { useCallback, useEffect, useState } from "react";

import type { ConversationSummary } from "@shared/types";

import {
  deleteConversation,
  getAuthState,
  getConversation,
  listConversations,
  signInWithGoogle,
} from "../../shared/api-client";
import { Button } from "../components/Button";
import type { RestoredChat } from "./AskTab";

type ListState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "loaded"; conversations: ConversationSummary[]; retentionDays: number }
  | { status: "error"; message: string };

function relativeTime(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}

export function RecentTab({ onOpen }: { onOpen: (chat: RestoredChat) => void }): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    const { sessionToken } = await getAuthState();
    if (!sessionToken) {
      setState({ status: "signed-out" });
      return;
    }
    try {
      const response = await listConversations();
      setState({ status: "loaded", conversations: response.conversations, retentionDays: response.retention_days });
    } catch (error) {
      setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (id: string) => {
    setBusyId(id);
    setActionError(null);
    try {
      const detail = await getConversation(id);
      if (!detail.slide) {
        setActionError("That chat's slide is no longer available.");
        return;
      }
      onOpen({ conversationId: detail.id, slide: detail.slide, messages: detail.messages });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id: string) => {
    setBusyId(id);
    setActionError(null);
    try {
      await deleteConversation(id);
      setState((prev) =>
        prev.status === "loaded" ? { ...prev, conversations: prev.conversations.filter((c) => c.id !== id) } : prev
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
    }
  };

  const signIn = async () => {
    try {
      await signInWithGoogle();
      await load();
    } catch (error) {
      setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <h2 className="text-base font-semibold text-slate-800">Recent chats</h2>

      {state.status === "loading" && <p className="text-sm text-slate-400">Loading…</p>}

      {state.status === "signed-out" && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-slate-200 p-4 shadow-subtle">
          <p className="text-sm text-slate-600">Sign in to keep your chats and pick them up on any device.</p>
          <Button onClick={() => void signIn()}>Sign in with Google</Button>
        </div>
      )}

      {state.status === "error" && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          <p>{state.message}</p>
          <button type="button" onClick={() => void load()} className="mt-2 font-medium underline underline-offset-2">
            Try again
          </button>
        </div>
      )}

      {actionError && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{actionError}</p>}

      {state.status === "loaded" && state.conversations.length === 0 && (
        <p className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-400">
          No chats yet. Capture a slide and ask a question to start one.
        </p>
      )}

      {state.status === "loaded" && state.conversations.length > 0 && (
        <ul className="flex flex-col gap-2">
          {state.conversations.map((conversation) => (
            <li
              key={conversation.id}
              className="flex items-center gap-2 rounded-md border border-slate-200 transition-colors duration-[120ms] hover:border-indigo-200 hover:bg-indigo-50/40"
            >
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => void open(conversation.id)}
                className="flex min-w-0 flex-1 flex-col gap-0.5 px-3 py-2.5 text-left disabled:opacity-50"
              >
                <span className="truncate text-sm font-medium text-slate-700">{conversation.title}</span>
                <span className="text-xs text-slate-400">{relativeTime(conversation.last_activity_at)}</span>
              </button>
              <button
                type="button"
                disabled={busyId !== null}
                onClick={() => void remove(conversation.id)}
                aria-label={`Delete chat: ${conversation.title}`}
                className="mr-2 flex h-7 w-7 flex-none items-center justify-center rounded-md text-slate-400 transition-colors duration-[120ms] hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {state.status === "loaded" && (
        <p className="text-xs text-slate-400">
          Chats are deleted {state.retentionDays} days after their last message. You can delete one sooner at any
          time.
        </p>
      )}
    </div>
  );
}
