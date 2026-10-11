/**
 * A tutoring chat about one quiz question. It opens with the student's
 * choice already stated, so the first answer explains that choice without
 * them typing anything; they can then ask follow-ups. Goes through POST
 * /chat in "tutor" mode, which grounds the model on the question, the
 * options, the choice and the slide it came from.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, createNote, streamChat } from "../../shared/api-client";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";

interface TutorMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

type SaveState = "saving" | "saved" | "failed";

export function TutorChat({
  quizId,
  seriesId,
  questionIndex,
  questionText,
  selectedIndex,
  correct,
}: {
  quizId: string;
  seriesId: string;
  questionIndex: number;
  questionText: string;
  selectedIndex: number | null;
  correct: boolean;
}): JSX.Element {
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Record<string, SaveState>>({});
  const conversationIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef(false);

  const ask = useCallback(
    async (text: string) => {
      setError(null);
      setStreaming(true);
      const answerId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: text },
        { id: answerId, role: "assistant", content: "" },
      ]);
      const abort = new AbortController();
      abortRef.current = abort;
      try {
        const request = {
          conversation_id: conversationIdRef.current,
          presentation_id: null,
          query_mode: "tutor",
          slide_id: null,
          object_id: null,
          message: text,
          quiz_id: quizId,
          question_index: questionIndex,
          selected_index: selectedIndex,
        } as const;
        for await (const event of streamChat(request, undefined, abort.signal)) {
          if (abort.signal.aborted) break;
          if (event.type === "delta") {
            setMessages((prev) => prev.map((m) => (m.id === answerId ? { ...m, content: m.content + event.text } : m)));
          } else if (event.type === "done") {
            conversationIdRef.current = event.data.conversation_id;
          } else {
            setError(event.data.message);
          }
        }
      } catch (caught) {
        if (!abort.signal.aborted) {
          setError(
            caught instanceof ApiError && caught.status === 429
              ? caught.message
              : `The explanation could not be loaded. ${caught instanceof Error ? caught.message : ""}`.trim()
          );
        }
      } finally {
        setMessages((prev) => prev.filter((m) => m.id !== answerId || m.content));
        setStreaming(false);
      }
    },
    [quizId, questionIndex, selectedIndex]
  );

  // The opening question is asked for the student, once.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void ask(
      selectedIndex === null
        ? "I skipped this one. Walk me through how to work it out."
        : correct
          ? "I got this right. Help me understand it more deeply."
          : `I chose ${String.fromCharCode(65 + selectedIndex)}. Walk me through why that's wrong.`
    );
    return () => abortRef.current?.abort();
  }, [ask, selectedIndex, correct]);

  const save = async (message: TutorMessage) => {
    setSaved((prev) => ({ ...prev, [message.id]: "saving" }));
    try {
      await createNote({ title: questionText.slice(0, 200), body: message.content, source: "ai", series_id: seriesId });
      setSaved((prev) => ({ ...prev, [message.id]: "saved" }));
    } catch {
      setSaved((prev) => ({ ...prev, [message.id]: "failed" }));
    }
  };

  return (
    <div className="flex flex-col gap-3 border-t border-slate-200 pt-4">
      <ul className="flex flex-col gap-3" aria-live="polite">
        {messages.map((message) =>
          message.role === "user" ? (
            <li key={message.id} className="max-w-[90%] self-end rounded-md bg-indigo-600 px-3 py-2 text-sm text-white">
              {message.content}
            </li>
          ) : (
            <li key={message.id} className="flex min-w-0 flex-col items-start gap-1">
              <div className="max-w-full overflow-x-auto rounded-md border border-indigo-100 bg-indigo-50/40 px-3.5 py-3 text-sm leading-relaxed text-slate-700 shadow-subtle">
                {message.content ? <MathText text={message.content} /> : <span className="text-slate-400">Thinking…</span>}
              </div>
              {message.content && !streaming && (
                <button
                  type="button"
                  disabled={saved[message.id] === "saving" || saved[message.id] === "saved"}
                  onClick={() => void save(message)}
                  className="rounded-sm px-2 py-1 text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:hover:bg-transparent"
                >
                  {saved[message.id] === "saved"
                    ? "Saved to notes"
                    : saved[message.id] === "saving"
                      ? "Saving…"
                      : saved[message.id] === "failed"
                        ? "Couldn't save. Try again"
                        : "Save to notes"}
                </button>
              )}
            </li>
          )
        )}
      </ul>

      {error && (
        <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const text = input.trim();
          if (!text || streaming) return;
          setInput("");
          void ask(text);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Answer, or ask a follow-up"
          aria-label="Reply to the tutor"
          disabled={streaming}
          className="min-w-0 flex-1 rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 transition-colors duration-[120ms] placeholder:text-slate-400 focus:border-indigo-400 disabled:opacity-50"
        />
        {streaming ? (
          <Button variant="secondary" onClick={() => abortRef.current?.abort()}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>
            Send
          </Button>
        )}
      </form>
    </div>
  );
}
