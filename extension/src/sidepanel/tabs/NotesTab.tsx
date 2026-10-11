/**
 * Notes: answers the student saved and notes they wrote, grouped by the
 * series they belong to. A note opens to be read, typeset the same way chat
 * answers are; Edit turns it into plain text to change or add to. Notes live
 * on the server and are kept until deleted.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import type { NoteOut } from "@shared/types";

import { createNote, deleteNote, getAuthState, listNotes, signInWithGoogle, updateNote } from "../../shared/api-client";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { relativeTime } from "../recent/library";
import { BackIcon, CloseIcon, SearchIcon } from "../recent/parts";

type ListState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "loaded"; notes: NoteOut[] }
  | { status: "error"; message: string };

/** The note being edited; `id` is null for one that has not been saved yet. */
interface Draft {
  id: string | null;
  title: string;
  body: string;
  savedTitle: string;
  savedBody: string;
}

const FIELD =
  "w-full rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 transition-colors duration-[120ms] placeholder:text-slate-400 focus:border-indigo-400";
const NO_TOPIC = "General";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const BACK_LINK =
  "-ml-1 flex items-center gap-1 self-start rounded-sm px-1 py-1 text-sm font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-50 hover:text-slate-700";

function NoteView({
  draft,
  editing,
  busy,
  error,
  onChange,
  onSave,
  onDelete,
  onBack,
  onEdit,
  onCancel,
}: {
  draft: Draft;
  editing: boolean;
  busy: boolean;
  error: string | null;
  onChange: (changes: Partial<Draft>) => void;
  onSave: () => void;
  onDelete: () => void;
  onBack: () => void;
  onEdit: () => void;
  onCancel: () => void;
}): JSX.Element {
  const back = (
    <button type="button" onClick={onBack} className={BACK_LINK}>
      <BackIcon />
      All notes
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
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          className="-ml-2 self-start rounded-sm px-2 py-1 text-xs font-medium text-red-700 transition-colors duration-[120ms] hover:bg-red-50 disabled:opacity-50 dark:text-red-300"
        >
          Delete note
        </button>
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

export function NotesTab(): JSX.Element {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [query, setQuery] = useState("");
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

  const groups = useMemo(() => {
    if (state.status !== "loaded") return [];
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const byTopic = new Map<string, NoteOut[]>();
    for (const note of state.notes) {
      const topic = note.topic ?? NO_TOPIC;
      const haystack = `${topic} ${note.title} ${note.body}`.toLowerCase();
      if (!words.every((word) => haystack.includes(word))) continue;
      byTopic.set(topic, [...(byTopic.get(topic) ?? []), note]);
    }
    // Notes arrive most recently edited first, so groups do too.
    return [...byTopic].map(([topic, notes]) => ({ topic, notes }));
  }, [state, query]);

  const open = (note: NoteOut) => {
    setEditorError(null);
    setEditing(false);
    setDraft({ id: note.id, title: note.title, body: note.body, savedTitle: note.title, savedBody: note.body });
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
          ? await createNote({ title: draft.title, body: draft.body, source: "user" })
          : await updateNote(draft.id, { title: draft.title, body: draft.body });
      setDraft({ id: saved.id, title: saved.title, body: saved.body, savedTitle: saved.title, savedBody: saved.body });
      setEditing(false);
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
          onChange={(changes) => setDraft({ ...draft, ...changes })}
          onSave={() => void save()}
          onDelete={() => void remove()}
          onBack={leaveNote}
          onEdit={() => setEditing(true)}
          onCancel={cancelEdit}
        />
      </div>
    );
  }

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-slate-800">Notes</h2>
        {state.status === "loaded" && (
          <Button
            onClick={() => {
              setEditorError(null);
              setEditing(true);
              setDraft({ id: null, title: "", body: "", savedTitle: "", savedBody: "" });
            }}
          >
            New note
          </Button>
        )}
      </div>

      {state.status === "loading" && (
        <ul className="flex animate-pulse flex-col gap-3" aria-label="Loading your notes">
          {[0, 1, 2].map((row) => (
            <li key={row} className="flex flex-col gap-2 rounded-md border border-slate-200 p-3" aria-hidden="true">
              <span className="h-3 w-2/3 rounded bg-slate-100" />
              <span className="h-3 w-full rounded bg-slate-100" />
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

          {groups.length === 0 && (
            <p className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
              No note matches "{query.trim()}".
            </p>
          )}

          {groups.map(({ topic, notes }) => (
            <section key={topic} className="flex flex-col gap-2">
              <h3 className="text-xs font-medium text-slate-500">{topic}</h3>
              <ul className="flex flex-col gap-2">
                {notes.map((note) => (
                  <li key={note.id}>
                    <button
                      type="button"
                      onClick={() => open(note)}
                      className="flex w-full flex-col gap-1 rounded-md border border-slate-200 bg-white p-3 text-left shadow-subtle transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
                    >
                      <span className="truncate text-sm font-semibold text-slate-800">
                        <MathText text={note.title} />
                      </span>
                      <span className="text-xs text-slate-400">
                        {note.source === "ai" ? "Saved answer" : "Your note"}, edited{" "}
                        {relativeTime(new Date(note.updated_at).getTime()).toLowerCase()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          <p className="text-xs text-slate-400">Notes are kept until you delete them.</p>
        </>
      )}
    </div>
  );
}
