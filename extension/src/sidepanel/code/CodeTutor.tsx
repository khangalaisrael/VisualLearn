/**
 * Asking the tutor about the code in the editor, without leaving the Code tab.
 * The student writes their own question (or presses a suggestion); the code,
 * and what happened when it last ran, are sent along with it. Follow-up
 * questions continue the same conversation, and the code is sent again only
 * when it, or its result, has changed since the last question.
 */

import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiError, streamChat } from "../../shared/api-client";
import { refreshUsage } from "../../shared/usage-store";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";

interface TutorMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function CodeTutor({
  context,
  suggestions,
  disabled,
  question,
}: {
  /** The code and its last run, described for the tutor. */
  context: string;
  /** Questions offered as one-press chips, fitting the last run. */
  suggestions: string[];
  /** Signed out: the box is shown, but nothing can be sent. */
  disabled: boolean;
  /** A question asked from elsewhere in the Code tab (such as "Explain this error"); `id` changes with each. */
  question?: { id: number; text: string } | null;
}): JSX.Element {
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<{ message: string; limited: boolean } | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  // The context the tutor was last given, so unchanged code is not sent twice.
  const sentContextRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (messages.length === 0) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
  }, [messages.length]);

  const ask = useCallback(
    async (question: string) => {
      const asked = question.trim();
      if (!asked || streaming || disabled) return;
      setError(null);
      setStreaming(true);
      const answerId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: asked },
        { id: answerId, role: "assistant", content: "" },
      ]);
      const withContext = sentContextRef.current !== context;
      const abort = new AbortController();
      abortRef.current = abort;
      try {
        const request = {
          conversation_id: conversationIdRef.current,
          presentation_id: null,
          query_mode: "general",
          slide_id: null,
          object_id: null,
          message: withContext ? `${context}\n\nMy question: ${asked}` : asked,
        } as const;
        for await (const event of streamChat(request, undefined, abort.signal)) {
          if (abort.signal.aborted) break;
          if (event.type === "delta") {
            setMessages((prev) => prev.map((m) => (m.id === answerId ? { ...m, content: m.content + event.text } : m)));
          } else if (event.type === "done") {
            conversationIdRef.current = event.data.conversation_id;
            sentContextRef.current = context;
            void refreshUsage();
          } else {
            setError({ message: event.data.message, limited: false });
          }
        }
      } catch (caught) {
        if (!abort.signal.aborted) {
          setError({
            message: caught instanceof Error ? caught.message : String(caught),
            limited: caught instanceof ApiError && caught.status === 429,
          });
        }
      } finally {
        // A reply stopped before any text arrived leaves nothing worth showing.
        setMessages((prev) => prev.filter((m) => m.id !== answerId || m.content));
        setStreaming(false);
      }
    },
    [context, disabled, streaming]
  );

  const send = () => {
    const question = input;
    setInput("");
    void ask(question);
  };

  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  // A question asked from the output panel ("Explain this error"), once per id.
  const askedRef = useRef<number | null>(null);
  useEffect(() => {
    if (!question || askedRef.current === question.id) return;
    askedRef.current = question.id;
    void ask(question.text);
  }, [question, ask]);

  const clear = () => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    conversationIdRef.current = null;
    sentContextRef.current = null;
  };

  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="Ask the tutor">
      <div className="scrollbar-thin flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-2">
        {messages.length === 0 ? (
          <p className="text-xs leading-relaxed text-slate-500">
            Ask about a line, an error, or what to change. Your code and its last result are sent with the question,
            and each question counts as a chat message.
          </p>
        ) : (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={clear}
              className="rounded-sm text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:text-slate-700 hover:underline"
            >
              Clear the conversation
            </button>
          </div>
        )}

        {messages.length > 0 && (
          <ul className="flex flex-col gap-2">
            {messages.map((message) =>
              message.role === "user" ? (
                <li
                  key={message.id}
                  className="max-w-[90%] self-end whitespace-pre-wrap break-words rounded-md bg-indigo-600 px-3 py-2 text-sm text-white"
                >
                  {message.content}
                </li>
              ) : (
                <li
                  key={message.id}
                  className="max-w-full overflow-x-auto rounded-md border border-amber-100 bg-amber-50/70 px-3.5 py-3 text-sm leading-relaxed text-slate-700 dark:border-indigo-100 dark:bg-indigo-50/40"
                >
                  {message.content ? <MathText text={message.content} /> : <span className="text-slate-400">Thinking…</span>}
                </li>
              )
            )}
          </ul>
        )}
        <div ref={endRef} />

        {error &&
          (error.limited ? (
            <p role="status" className="rounded-md border border-violet-100 bg-violet-50/50 p-3 text-sm text-slate-600">
              {error.message}
            </p>
          ) : (
            <p role="alert" className="rounded-sm bg-red-50 p-3 text-sm text-red-700 dark:text-red-300">
              {error.message}
            </p>
          ))}
      </div>

      <div className="flex flex-none flex-col gap-2 border-t border-slate-100 px-3 py-2">
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={streaming || disabled}
                onClick={() => void ask(suggestion)}
                className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 transition-colors duration-[120ms] hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-300"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKey}
            rows={1}
            maxLength={2000}
            disabled={disabled}
            aria-label="Ask about this code"
            placeholder={disabled ? "Sign in to ask the tutor" : "Ask about your code"}
            className="max-h-28 min-w-0 flex-1 resize-none rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 transition-colors duration-[120ms] [field-sizing:content] placeholder:text-slate-400 focus:border-indigo-400 disabled:opacity-50"
          />
          <Button onClick={send} disabled={streaming || disabled || !input.trim()}>
            {streaming ? "Answering…" : "Ask"}
          </Button>
        </div>
      </div>
    </section>
  );
}
