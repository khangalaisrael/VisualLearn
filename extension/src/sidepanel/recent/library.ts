/**
 * The data behind "Recent": the user's captures as a list of series.
 *
 * Signed in, series come from the server (sorted by topic) and thumbnails
 * from this browser, matched by slide id. Signed out, there is no sorter, so
 * each page's local captures form one series. Searching and filtering happen
 * here, on data already loaded: no request, no model call.
 */

import type { ContentKind, SeriesCapture } from "@shared/types";

import { getAuthState, getSeries } from "../../shared/api-client";
import { type CaptureRecord, LOCAL_RETENTION_DAYS, listCaptures, purgeOlderThan } from "../../shared/capture-store";

export interface LibraryCapture {
  slideId: string;
  summary: string;
  subtopic: string | null;
  kind: ContentKind;
  capturedAt: number;
  followUps: number;
  latestConversationId: string | null;
  thumbnail: Blob | null;
  pageTitle: string;
  /** Its place in the series, counted from 1 in the order the slides were captured. */
  position: number;
}

export interface LibrarySeries {
  id: string;
  category: string;
  title: string;
  coverSlideId: string | null;
  lastActivity: number;
  /** In the order they were captured, like a playlist. */
  captures: LibraryCapture[];
  /** A real, server-side series: it can be renamed, re-covered and moved into. */
  sorted: boolean;
  /** A favourite: listed before the others. */
  starred: boolean;
}

export interface Library {
  series: LibrarySeries[];
  retentionDays: number;
  signedIn: boolean;
}

/** Captures the sorter has not placed yet are shown as one group under this id. */
export const UNSORTED_ID = "unsorted";
const LOCAL_CATEGORY = "On this device";

/** Puts a series' slides in capture order and numbers them. */
function inOrder(captures: Omit<LibraryCapture, "position">[]): LibraryCapture[] {
  return [...captures]
    .sort((a, b) => a.capturedAt - b.capturedAt)
    .map((capture, index) => ({ ...capture, position: index + 1 }));
}

function fromServer(capture: SeriesCapture, thumbnails: Map<string, Blob | null>): Omit<LibraryCapture, "position"> {
  return {
    slideId: capture.slide_id,
    summary: capture.summary,
    subtopic: capture.subtopic,
    kind: capture.kind,
    capturedAt: new Date(capture.created_at).getTime(),
    // A user message and its answer are two saved messages.
    followUps: capture.conversations.reduce((sum, chat) => sum + Math.ceil(chat.message_count / 2), 0),
    latestConversationId: capture.conversations[0]?.id ?? null,
    thumbnail: thumbnails.get(capture.slide_id) ?? null,
    pageTitle: capture.page_title,
  };
}

function groupLocal(records: CaptureRecord[]): LibrarySeries[] {
  const groups = new Map<string, LibrarySeries>();
  for (const record of records) {
    const capture: LibraryCapture = {
      position: 0, // numbered below, once the group is complete
      slideId: record.slide_id,
      summary: record.summary,
      subtopic: null,
      kind: "lecture",
      capturedAt: record.capturedAt,
      followUps: 0,
      latestConversationId: null,
      thumbnail: record.thumbnail,
      pageTitle: record.title,
    };
    const existing = groups.get(record.presentation_id);
    if (existing) {
      existing.captures.push(capture);
    } else {
      groups.set(record.presentation_id, {
        id: record.presentation_id,
        category: LOCAL_CATEGORY,
        title: record.title,
        coverSlideId: null,
        lastActivity: record.capturedAt,
        captures: [capture],
        sorted: false,
        starred: false,
      });
    }
  }
  return [...groups.values()]
    .map((group) => ({ ...group, captures: inOrder(group.captures) }))
    .sort((a, b) => b.lastActivity - a.lastActivity);
}

export async function loadLibrary(): Promise<Library> {
  const { sessionToken } = await getAuthState();
  await purgeOlderThan(LOCAL_RETENTION_DAYS).catch(() => undefined);
  const local = await listCaptures().catch(() => [] as CaptureRecord[]);

  if (!sessionToken) {
    // Only captures made while signed out, never a previous account's.
    const own = local.filter((record) => (record.owner ?? "") === "");
    return { series: groupLocal(own), retentionDays: LOCAL_RETENTION_DAYS, signedIn: false };
  }

  const response = await getSeries();
  const thumbnails = new Map(local.map((record) => [record.slide_id, record.thumbnail]));
  const series: LibrarySeries[] = response.series.map((item) => ({
    id: item.id,
    category: item.category,
    title: item.title,
    coverSlideId: item.cover_slide_id,
    lastActivity: new Date(item.last_activity_at).getTime(),
    captures: inOrder(item.captures.map((capture) => fromServer(capture, thumbnails))),
    sorted: true,
    starred: item.starred,
  }));
  // Favourites first; within each part the server's order (latest activity first) is kept.
  series.sort((a, b) => Number(b.starred) - Number(a.starred));
  if (response.unsorted.length > 0) {
    const captures = inOrder(response.unsorted.map((capture) => fromServer(capture, thumbnails)));
    series.push({
      id: UNSORTED_ID,
      category: "Not sorted yet",
      title: "Waiting to be sorted",
      coverSlideId: null,
      lastActivity: Math.max(...captures.map((capture) => capture.capturedAt)),
      captures,
      sorted: false,
      starred: false,
    });
  }
  return { series, retentionDays: response.retention_days, signedIn: true };
}

/** The chosen cover's picture, or else the first slide that has one on this device. */
export function coverOf(series: LibrarySeries): Blob | null {
  const chosen = series.captures.find((capture) => capture.slideId === series.coverSlideId)?.thumbnail;
  return chosen ?? series.captures.find((capture) => capture.thumbnail)?.thumbnail ?? null;
}

export function categoriesOf(series: LibrarySeries[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const item of series) counts.set(item.category, (counts.get(item.category) ?? 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => a.name.localeCompare(b.name));
}

function matches(text: string, words: string[]): boolean {
  const lowered = text.toLowerCase();
  return words.every((word) => lowered.includes(word));
}

/** A series to show in the list. `slideMatches` is set when a search matched
 * particular slides rather than the series' own name: those slides are then
 * listed under it. */
export interface SeriesHit {
  series: LibrarySeries;
  slideMatches: LibraryCapture[] | null;
}

/**
 * Series in `category` (null = all) that match every word of `query`. A
 * series whose own name matches is shown as it is; otherwise it is shown with
 * the slides that match, so a search for one slide finds it.
 */
export function filterLibrary(series: LibrarySeries[], query: string, category: string | null): SeriesHit[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const inCategory = category === null ? series : series.filter((item) => item.category === category);
  if (words.length === 0) return inCategory.map((item) => ({ series: item, slideMatches: null }));

  const found: SeriesHit[] = [];
  for (const item of inCategory) {
    const name = `${item.category} ${item.title}`;
    if (matches(name, words)) {
      found.push({ series: item, slideMatches: null });
      continue;
    }
    const slides = item.captures.filter((capture) =>
      matches(`${name} ${capture.subtopic ?? ""} ${capture.summary} ${capture.pageTitle}`, words)
    );
    if (slides.length > 0) found.push({ series: item, slideMatches: slides });
  }
  return found;
}

export function relativeTime(timestamp: number): string {
  const minutes = Math.floor((Date.now() - timestamp) / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}

export function countLabel(count: number, singular: string): string {
  return `${count} ${count === 1 ? singular : `${singular}s`}`;
}
