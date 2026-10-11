/**
 * Notes: answers the student saved and notes they wrote, organised the way
 * Recent is. Each series that has notes is a card with its name and category;
 * pressing it opens that series' notes. A note opens to be read, typeset the
 * same way chat answers are; Edit turns it into plain text to change or add
 * to. Notes live on the server and are kept until deleted.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { NoteOut } from "@shared/types";

import { createNote, deleteNote, getAuthState, listNotes, signInWithGoogle, updateNote } from "../../shared/api-client";
import { openPrintView } from "../../shared/print";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { countLabel, relativeTime } from "../recent/library";
import { BackIcon, CloseIcon, ForwardIcon, SearchIcon, StarIcon } from "../recent/parts";

type ListState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "loaded"; notes: NoteOut[] }
  | { status: "error"; message: string };

/** The note being edited; `id` is null for one that has not been saved yet. */
interface Draft {
  id: string | null;
  /** The series a new note will be filed under, when it is written from a series' page. */
  seriesId: string | null;
  starred: boolean;
  title: string;
  body: string;
  savedTitle: string;
  savedBody: string;
}

const FIELD =
  "w-full rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 transition-colors duration-[120ms] placeholder:text-slate-400 focus:border-indigo-400";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const BACK_LINK =
  "-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700";

const NOTE_ACTION =
  "rounded-sm px-2 py-1.5 text-xs font-medium transition-colors duration-[120ms] disabled:opacity-50";

function NoteView({
  draft,
  editing,
  busy,
  error,
  backLabel,
  onChange,
  onSave,
  onDelete,
  onBack,
  onEdit,
  onCancel,
  onToggleStar,
}: {
  draft: Draft;
  editing: boolean;
  busy: boolean;
  error: string | null;
  /** Where Back goes: the series' notes, or the list of all notes. */
  backLabel: string;
  onChange: (changes: Partial<Draft>) => void;
  onSave: () => void;
  onDelete: () => void;
  onBack: () => void;
  onEdit: () => void;
  onCancel: () => void;
  onToggleStar: () => void;
}): JSX.Element {
  const back = (
    <button type="button" onClick={onBack} className={BACK_LINK}>
      <BackIcon />
      <span className="truncate">{backLabel}</span>
    </button>
  );
  const problem = error && (
    <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
      {error}
    </p>
  );

  if (!editing) {
    return (
      <div className="flex flex-1 flex-col gap-4">
        {back}
        <div className="flex items-start justify-between gap-3">
          {/* A title taken from a question can carry math, like the note itself. */}
          <h2 className="min-w-0 text-lg font-semibold leading-snug text-slate-800">
            <MathText text={draft.savedTitle} />
          </h2>
          <Button variant="secondary" onClick={onEdit} className="flex-none">
            Edit
          </Button>
        </div>
        <div className="overflow-x-auto text-sm leading-relaxed text-slate-700">
          <MathText text={draft.savedBody} />
        </div>
        {problem}
        <div className="-ml-2 flex flex-wrap items-center gap-1 border-t border-slate-200 pt-3">
          <button
            type="button"
            disabled={busy}
            aria-pressed={draft.starred}
            onClick={onToggleStar}
            className={`${NOTE_ACTION} flex items-center gap-1 hover:bg-slate-100 ${
              draft.starred ? "text-amber-700 dark:text-amber-300" : "text-slate-600"
            }`}
          >
            <StarIcon filled={draft.starred} />
            {draft.starred ? "Favourite" : "Add to favourites"}
          </button>
          <button
            type="button"
            onClick={() => void openPrintView(draft.savedTitle, draft.savedBody)}
            className={`${NOTE_ACTION} text-slate-600 hover:bg-slate-100`}
          >
            Save as PDF
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            className={`${NOTE_ACTION} text-red-700 hover:bg-red-50 dark:text-red-300`}
          >
            Delete note
          </button>
        </div>
      </div>
    );
  }

  const dirty = draft.title !== draft.savedTitle || draft.body !== draft.savedBody;
  return (
    <form
      className="flex flex-1 flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      {back}
      <h2 className="text-base font-semibold text-slate-800">{draft.id === null ? "New note" : "Edit note"}</h2>
      <label className="flex flex-col gap-2 text-xs font-medium text-slate-600">
        Title
        <input
          className={FIELD}
          value={draft.title}
          maxLength={200}
          placeholder="Left blank, the first line is used"
          onChange={(event) => onChange({ title: event.target.value })}
        />
      </label>
      <label className="flex flex-1 flex-col gap-2 text-xs font-medium text-slate-600">
        Note
        <textarea
          id="note-body"
          className={`${FIELD} min-h-[320px] flex-1 resize-none font-mono text-[13px] font-normal leading-relaxed`}
          value={draft.body}
          maxLength={20_000}
          placeholder="Write your note. Add to a saved answer in your own words."
          onChange={(event) => onChange({ body: event.target.value })}
        />
      </label>
      <p className="text-xs text-slate-400">
        Math between $ signs, **bold**, # headings and ``` code blocks are typeset once you save.
      </p>
      {problem}
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={busy || !draft.body.trim() || (!dirty && draft.id !== null)}>
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The notes of one series, shown as one card in the list, the way Recent shows a series. */
interface NoteGroup {
  key: string;
  /** The series new notes written here are filed under; null when there is none to file under. */
  seriesId: string | null;
  title: string;
  category: string;
  /** Favourites first, then most recently edited first. */
  notes: NoteOut[];
  /** The note edited last, for the card's "edited ..." line. */
  latest: NoteOut;
}

/** A group to show in the list. `noteMatches` is set when a search matched
 * particular notes rather than the group's own name: those are listed under it. */
interface GroupHit {
  group: NoteGroup;
  noteMatches: NoteOut[] | null;
}

const GENERAL_KEY = "general";

function groupNotes(notes: NoteOut[]): NoteGroup[] {
  const groups = new Map<string, NoteGroup>();
  // Notes arrive most recently edited first, so groups come out in that order too.
  for (const note of notes) {
    const key = note.series_id ?? (note.topic ? `topic:${note.topic}` : GENERAL_KEY);
    const existing = groups.get(key);
    if (existing) {
      existing.notes.push(note);
      continue;
    }
    groups.set(key, {
      key,
      // A series that has since gone (its slides expired) can't take new notes.
      seriesId: note.category !== null ? note.series_id : null,
      title: note.topic ?? "General",
      category: note.category ?? (note.topic ? "Its slides are no longer in Recent" : "Not tied to a series"),
      notes: [note],
      latest: note,
    });
  }
  for (const group of groups.values()) group.notes.sort((a, b) => Number(b.starred) - Number(a.starred));
  return [...groups.values()];
}

function filterGroups(groups: NoteGroup[], query: string): GroupHit[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return groups.map((group) => ({ group, noteMatches: null }));
  const has = (text: string) => words.every((word) => text.toLowerCase().includes(word));

  const hits: GroupHit[] = [];
  for (const group of groups) {
    const name = `${group.category} ${group.title}`;
    if (has(name)) {
      hits.push({ group, noteMatches: null });
      continue;
    }
    const notes = group.notes.filter((note) => has(`${name} ${note.title} ${note.body}`));
    if (notes.length > 0) hits.push({ group, noteMatches: notes });
  }
  return hits;
}

function edited(note: NoteOut): string {
  return relativeTime(new Date(note.updated_at).getTime()).toLowerCase();
}

const CHIP = "flex flex-none items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-[120ms]";
const CHIP_ON = "border-indigo-600 bg-indigo-600 text-white";
const CHIP_OFF = "border-slate-200 text-slate-600 hover:bg-slate-50";

/** One note as a row to press. `framed` gives it its own card; unframed it sits
 * inside a group's card. `series` names where it is filed, for a list that mixes series. */
function NoteRow({
  note,
  framed,
  series,
  onOpen,
}: {
  note: NoteOut;
  framed: boolean;
  series?: string;
  onOpen: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex w-full flex-col gap-0.5 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100 ${
        framed ? "rounded-md border border-slate-200 bg-white p-3 shadow-subtle" : "rounded-sm px-3 py-2"
      }`}
    >
      <span className="flex items-center gap-1.5 text-sm font-medium text-slate-800">
        {note.starred && (
          <span className="flex-none text-amber-600 dark:text-amber-300" title="Favourite">
            <StarIcon filled />
          </span>
        )}
        <span className="truncate">
          <MathText text={note.title} />
        </span>
      </span>
      <span className="text-xs text-slate-400">
        {series ? `${series}, ` : ""}
        {note.source === "ai" ? (series ? "saved answer" : "Saved answer") : series ? "your note" : "Your note"}, edited{" "}
        {edited(note)}
      </span>
    </button>
  );
}

export function NotesTab(): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [query, setQuery] = useState("");
  // The group whose page is open; null on the list of groups.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // Show only favourite notes, from every series, in one list.
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  // A note opens to be read; a new note, or one being changed, is in the editor.
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { sessionToken } = await getAuthState();
      if (!sessionToken) {
        setState({ status: "signed-out" });
        return;
      }
      setState({ status: "loaded", notes: (await listNotes()).notes });
    } catch (error) {
      setState({ status: "error", message: errorText(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => (state.status === "loaded" ? groupNotes(state.notes) : []), [state]);
  const hits = useMemo(() => filterGroups(groups, query), [groups, query]);
  const favourites = useMemo(() => {
    if (state.status !== "loaded") return [];
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return state.notes.filter(
      (note) => note.starred && words.every((word) => `${note.topic ?? ""} ${note.title} ${note.body}`.toLowerCase().includes(word))
    );
  }, [state, query]);
  // A group disappears with its last note: its page then falls back to the list.
  const selected = groups.find((group) => group.key === selectedKey) ?? null;

  const open = (note: NoteOut) => {
    setEditorError(null);
    setEditing(false);
    setDraft({
      id: note.id,
      seriesId: note.series_id,
      starred: note.starred,
      title: note.title,
      body: note.body,
      savedTitle: note.title,
      savedBody: note.body,
    });
  };

  const startNote = (seriesId: string | null) => {
    setEditorError(null);
    setEditing(true);
    setDraft({ id: null, seriesId, starred: false, title: "", body: "", savedTitle: "", savedBody: "" });
  };

  /** True when it is fine to throw away what is in the editor. */
  const mayDiscard = () => {
    const dirty =
      editing && draft !== null && (draft.title !== draft.savedTitle || draft.body !== draft.savedBody);
    return !dirty || window.confirm("Leave without saving your changes?");
  };

  const leaveNote = () => {
    if (mayDiscard()) setDraft(null);
  };

  /** Cancel in the editor: back to reading the saved note, or out of a note that was never saved. */
  const cancelEdit = () => {
    if (!draft || !mayDiscard()) return;
    if (draft.id === null) {
      setDraft(null);
      return;
    }
    setDraft({ ...draft, title: draft.savedTitle, body: draft.savedBody });
    setEditing(false);
  };

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setEditorError(null);
    try {
      const saved =
        draft.id === null
          ? await createNote({
              title: draft.title,
              body: draft.body,
              source: "user",
              ...(draft.seriesId ? { series_id: draft.seriesId } : {}),
            })
          : await updateNote(draft.id, { title: draft.title, body: draft.body });
      setDraft({
        id: saved.id,
        seriesId: saved.series_id,
        starred: saved.starred,
        title: saved.title,
        body: saved.body,
        savedTitle: saved.title,
        savedBody: saved.body,
      });
      setEditing(false);
      await load();
    } catch (error) {
      setEditorError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const toggleStar = async () => {
    if (!draft?.id) return;
    setBusy(true);
    setEditorError(null);
    try {
      const saved = await updateNote(draft.id, { starred: !draft.starred });
      setDraft({ ...draft, starred: saved.starred });
      await load();
    } catch (error) {
      setEditorError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!draft?.id || !window.confirm("Delete this note for good?")) return;
    setBusy(true);
    setEditorError(null);
    try {
      await deleteNote(draft.id);
      setDraft(null);
      await load();
    } catch (error) {
      setEditorError(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const signIn = async () => {
    try {
      await signInWithGoogle();
      setState({ status: "loading" });
      await load();
    } catch (error) {
      setState({ status: "error", message: errorText(error) });
    }
  };

  if (draft) {
    return (
      <div className="scrollbar-thin flex flex-1 flex-col overflow-y-auto p-4">
        <NoteView
          draft={draft}
          editing={editing}
          busy={busy}
          error={editorError}
          backLabel={selected ? selected.title : "All notes"}
          onChange={(changes) => setDraft({ ...draft, ...changes })}
          onSave={() => void save()}
          onDelete={() => void remove()}
          onBack={leaveNote}
          onEdit={() => setEditing(true)}
          onCancel={cancelEdit}
          onToggleStar={() => void toggleStar()}
        />
      </div>
    );
  }

  if (selected) {
    return (
      <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <button type="button" onClick={() => setSelectedKey(null)} className={BACK_LINK}>
          <BackIcon />
          All notes
        </button>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <p className="text-xs font-medium text-indigo-600 dark:text-indigo-300">{selected.category}</p>
            <h2 className="text-lg font-semibold leading-snug text-slate-800">{selected.title}</h2>
            <p className="text-xs text-slate-400">{countLabel(selected.notes.length, "note")}</p>
          </div>
          <Button onClick={() => startNote(selected.seriesId)} className="flex-none">
            New note
          </Button>
        </div>
        <ul className="flex flex-col gap-2">
          {selected.notes.map((note) => (
            <li key={note.id}>
              <NoteRow note={note} framed onOpen={() => open(note)} />
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-slate-800">Notes</h2>
        {state.status === "loaded" && <Button onClick={() => startNote(null)}>New note</Button>}
      </div>

      {state.status === "loading" && (
        <ul className="flex animate-pulse flex-col gap-3" aria-label="Loading your notes">
          {[0, 1, 2].map((row) => (
            <li key={row} className="flex flex-col gap-2 rounded-md border border-slate-200 p-4" aria-hidden="true">
              <span className="h-3 w-2/3 rounded bg-slate-100" />
              <span className="h-3 w-1/2 rounded bg-slate-100" />
              <span className="h-3 w-1/3 rounded bg-slate-100" />
            </li>
          ))}
        </ul>
      )}

      {state.status === "error" && (
        <div role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          <p>{state.message}</p>
          <button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              void load();
            }}
            className="mt-2 font-medium underline underline-offset-2"
          >
            Try again
          </button>
        </div>
      )}

      {state.status === "signed-out" && (
        <div className="flex flex-col items-start gap-3 rounded-md border border-slate-200 p-4 shadow-subtle">
          <p className="text-sm text-slate-600">Sign in to save answers as notes and write your own.</p>
          <Button onClick={() => void signIn()}>Sign in with Google</Button>
        </div>
      )}

      {state.status === "loaded" && state.notes.length === 0 && (
        <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
          No notes yet. Save an answer from a chat, or start one with New note.
        </p>
      )}

      {state.status === "loaded" && state.notes.length > 0 && (
        <>
          <div className="relative">
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
              <SearchIcon />
            </span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search notes"
              aria-label="Search notes"
              className={`${FIELD} pl-9 pr-9 [&::-webkit-search-cancel-button]:hidden`}
            />
            {query.trim() !== "" && (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="Clear search"
                className="absolute inset-y-0 right-1 my-auto flex h-7 w-7 items-center justify-center rounded-sm text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <CloseIcon />
              </button>
            )}
          </div>

          <div className="flex gap-2" role="group" aria-label="Which notes to show">
            <button
              type="button"
              aria-pressed={!favouritesOnly}
              onClick={() => setFavouritesOnly(false)}
              className={`${CHIP} ${favouritesOnly ? CHIP_OFF : CHIP_ON}`}
            >
              All
            </button>
            <button
              type="button"
              aria-pressed={favouritesOnly}
              onClick={() => setFavouritesOnly(true)}
              className={`${CHIP} ${favouritesOnly ? CHIP_ON : CHIP_OFF}`}
            >
              <StarIcon filled={favouritesOnly} />
              Favourites
            </button>
          </div>

          {favouritesOnly ? (
            favourites.length === 0 ? (
              <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                {query.trim()
                  ? `No favourite note matches "${query.trim()}".`
                  : "No favourite notes yet. Open a note and press Add to favourites to keep it here."}
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {favourites.map((note) => (
                  <li key={note.id}>
                    <NoteRow note={note} framed series={note.topic ?? "General"} onOpen={() => open(note)} />
                  </li>
                ))}
              </ul>
            )
          ) : hits.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
              No note matches "{query.trim()}".
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {hits.map(({ group, noteMatches }) => (
                <li key={group.key} className="rounded-md border border-slate-200 bg-white shadow-subtle">
                  <button
                    type="button"
                    onClick={() => setSelectedKey(group.key)}
                    className="flex w-full items-center gap-3 rounded-md px-4 py-3 text-left transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
                  >
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="line-clamp-2 text-sm font-semibold leading-snug text-slate-800">{group.title}</span>
                      <span className="truncate text-xs text-slate-500">{group.category}</span>
                      <span className="text-xs text-slate-400">
                        {countLabel(group.notes.length, "note")}, edited {edited(group.latest)}
                      </span>
                    </span>
                    <span className="flex-none text-slate-400">
                      <ForwardIcon />
                    </span>
                  </button>
                  {noteMatches && (
                    <ul className="flex flex-col border-t border-slate-100 p-1" aria-label={`Matching notes in ${group.title}`}>
                      {noteMatches.map((note) => (
                        <li key={note.id}>
                          <NoteRow note={note} framed={false} onOpen={() => open(note)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs text-slate-400">Notes are kept until you delete them.</p>
        </>
      )}
    </div>
  );
}
