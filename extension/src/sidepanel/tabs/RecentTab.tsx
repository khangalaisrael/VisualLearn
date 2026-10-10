/**
 * Recent captures, grouped by lecture. Signed in, the text comes from the
 * server (so it follows the account across devices) and thumbnails from this
 * browser, matched by slide id; signed out, everything is the local copy.
 * How long things are kept comes from the server, never hardcoded here.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  deleteLecture,
  deleteSlide,
  getAuthState,
  getConversation,
  getLectures,
  getSlide,
  signInWithGoogle,
} from "../../shared/api-client";
import {
  type CaptureRecord,
  LOCAL_RETENTION_DAYS,
  deleteCapture,
  deleteLectureCaptures,
  listCaptures,
  purgeOlderThan,
} from "../../shared/capture-store";
import { Button } from "../components/Button";
import type { RestoredChat } from "./AskTab";

interface CaptureItem {
  slideId: string;
  summary: string;
  capturedAt: number;
  followUps: number;
  latestConversationId: string | null;
  thumbnail: Blob | null;
}

interface LectureGroup {
  id: string;
  title: string;
  lastActivity: number;
  captures: CaptureItem[];
}

type ListState =
  | { status: "loading" }
  | { status: "loaded"; groups: LectureGroup[]; retentionDays: number; signedIn: boolean }
  | { status: "error"; message: string };

function relativeTime(timestamp: number): string {
  const minutes = Math.floor((Date.now() - timestamp) / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}

function groupLocal(records: CaptureRecord[]): LectureGroup[] {
  const groups = new Map<string, LectureGroup>();
  for (const record of records) {
    const existing = groups.get(record.presentation_id);
    const item: CaptureItem = {
      slideId: record.slide_id,
      summary: record.summary,
      capturedAt: record.capturedAt,
      followUps: 0,
      latestConversationId: null,
      thumbnail: record.thumbnail,
    };
    if (existing) {
      existing.captures.push(item);
    } else {
      groups.set(record.presentation_id, {
        id: record.presentation_id,
        title: record.title,
        lastActivity: record.capturedAt,
        captures: [item],
      });
    }
  }
  return [...groups.values()].sort((a, b) => b.lastActivity - a.lastActivity);
}

function Thumbnail({ blob }: { blob: Blob | null }): JSX.Element {
  const url = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  return url ? (
    <img src={url} alt="" className="h-12 w-[72px] flex-none rounded border border-slate-200 object-cover" />
  ) : (
    <div className="h-12 w-[72px] flex-none rounded border border-slate-100 bg-slate-50" aria-hidden="true" />
  );
}

export function RecentTab({ onOpen }: { onOpen: (chat: RestoredChat) => void }): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const { sessionToken } = await getAuthState();
      await purgeOlderThan(LOCAL_RETENTION_DAYS).catch(() => undefined);
      const local = await listCaptures().catch(() => [] as CaptureRecord[]);

      let groups: LectureGroup[];
      let retentionDays = LOCAL_RETENTION_DAYS;
      if (sessionToken) {
        const response = await getLectures();
        retentionDays = response.retention_days;
        const thumbnails = new Map(local.map((record) => [record.slide_id, record.thumbnail]));
        groups = response.lectures.map((lecture) => ({
          id: lecture.id,
          title: lecture.title,
          lastActivity: new Date(lecture.last_activity_at).getTime(),
          captures: lecture.captures.map((capture) => ({
            slideId: capture.slide_id,
            summary: capture.summary,
            capturedAt: new Date(capture.created_at).getTime(),
            // A user message and its answer are two saved messages.
            followUps: capture.conversations.reduce((sum, chat) => sum + Math.ceil(chat.message_count / 2), 0),
            latestConversationId: capture.conversations[0]?.id ?? null,
            thumbnail: thumbnails.get(capture.slide_id) ?? null,
          })),
        }));
      } else {
        // Signed out: only captures made while signed out, never a previous account's.
        groups = groupLocal(local.filter((record) => (record.owner ?? "") === ""));
      }
      setState({ status: "loaded", groups, retentionDays, signedIn: Boolean(sessionToken) });
      setExpanded(new Set(groups[0] ? [groups[0].id] : []));
    } catch (error) {
      setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const open = async (capture: CaptureItem) => {
    setBusy(true);
    setActionError(null);
    try {
      if (capture.latestConversationId) {
        const detail = await getConversation(capture.latestConversationId);
        if (detail.slide) {
          onOpen({ conversationId: detail.id, slide: detail.slide, messages: detail.messages });
          return;
        }
      }
      onOpen({ conversationId: null, slide: await getSlide(capture.slideId), messages: [] });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const removeFromState = (predicate: (group: LectureGroup, capture: CaptureItem | null) => boolean) =>
    setState((prev) =>
      prev.status === "loaded"
        ? {
            ...prev,
            groups: prev.groups
              .filter((group) => !predicate(group, null))
              .map((group) => ({ ...group, captures: group.captures.filter((c) => !predicate(group, c)) }))
              .filter((group) => group.captures.length > 0),
          }
        : prev
    );

  const removeCapture = async (capture: CaptureItem, signedIn: boolean) => {
    setBusy(true);
    setActionError(null);
    try {
      if (signedIn) await deleteSlide(capture.slideId);
      await deleteCapture(capture.slideId).catch(() => undefined);
      removeFromState((_, c) => c?.slideId === capture.slideId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const removeLecture = async (group: LectureGroup, signedIn: boolean) => {
    if (!window.confirm(`Delete "${group.title}" and its ${group.captures.length} capture(s) and chats?`)) return;
    setBusy(true);
    setActionError(null);
    try {
      if (signedIn) await deleteLecture(group.id);
      await deleteLectureCaptures(group.id).catch(() => undefined);
      removeFromState((g, c) => c === null && g.id === group.id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
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
      <h2 className="text-base font-semibold text-slate-800">Recent</h2>

      {state.status === "loading" && <p className="text-sm text-slate-400">Loading…</p>}

      {state.status === "error" && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          <p>{state.message}</p>
          <button type="button" onClick={() => void load()} className="mt-2 font-medium underline underline-offset-2">
            Try again
          </button>
        </div>
      )}

      {actionError && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">{actionError}</p>}

      {state.status === "loaded" && !state.signedIn && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-slate-200 p-4 shadow-subtle">
          <p className="text-sm text-slate-600">Sign in to keep your chats and pick them up on any device.</p>
          <Button onClick={() => void signIn()}>Sign in with Google</Button>
        </div>
      )}

      {state.status === "loaded" && state.groups.length === 0 && (
        <p className="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-400">
          No captures yet. Capture a slide to see it here.
        </p>
      )}

      {state.status === "loaded" &&
        state.groups.map((group) => {
          const isOpen = expanded.has(group.id);
          return (
            <section key={group.id} className="rounded-lg border border-slate-200 shadow-subtle">
              <div className="flex items-center gap-1 pr-2">
                <button
                  type="button"
                  onClick={() => toggle(group.id)}
                  aria-expanded={isOpen}
                  className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left"
                >
                  <span className="text-xs text-slate-400" aria-hidden="true">
                    {isOpen ? "▾" : "▸"}
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-sm font-medium text-slate-800">{group.title}</span>
                    <span className="text-xs text-slate-400">
                      {group.captures.length} {group.captures.length === 1 ? "capture" : "captures"} ·{" "}
                      {relativeTime(group.lastActivity)}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void removeLecture(group, state.signedIn)}
                  aria-label={`Delete lecture: ${group.title}`}
                  className="flex h-7 w-7 flex-none items-center justify-center rounded-md text-slate-400 transition-colors duration-[120ms] hover:bg-red-50 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-50"
                >
                  ✕
                </button>
              </div>

              {isOpen && (
                <ul className="flex flex-col gap-1 border-t border-slate-100 p-2">
                  {group.captures.map((capture) => (
                    <li
                      key={capture.slideId}
                      className="flex items-start gap-1 rounded-md transition-colors duration-[120ms] hover:bg-indigo-50/40"
                    >
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void open(capture)}
                        className="flex min-w-0 flex-1 gap-3 p-2 text-left disabled:opacity-50"
                      >
                        <Thumbnail blob={capture.thumbnail} />
                        <span className="flex min-w-0 flex-1 flex-col gap-1">
                          <span className="line-clamp-2 text-sm text-slate-700">
                            {capture.summary || "Captured slide"}
                          </span>
                          <span className="flex items-center gap-2 text-xs text-slate-400">
                            {relativeTime(capture.capturedAt)}
                            {capture.followUps > 0 && (
                              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-600 dark:text-indigo-300">
                                {capture.followUps} {capture.followUps === 1 ? "follow-up" : "follow-ups"}
                              </span>
                            )}
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void removeCapture(capture, state.signedIn)}
                        aria-label="Delete this capture"
                        className="mt-1 flex h-7 w-7 flex-none items-center justify-center rounded-md text-slate-300 transition-colors duration-[120ms] hover:bg-red-50 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-50"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}

      {state.status === "loaded" && (
        <p className="text-xs text-slate-400">
          Captures and chats are deleted {state.retentionDays} days after they were made. Thumbnails stay on this
          device only. You can delete anything sooner.
        </p>
      )}
    </div>
  );
}
