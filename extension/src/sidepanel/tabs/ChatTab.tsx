/**
 * Chat: an open conversation with the tutor that is not about a captured
 * slide. Ask anything; the Ask tab is where a slide is discussed. Goes through
 * POST /chat in "general" mode. Signed in, the chat is saved like any other
 * and the last one is picked up again when the panel is reopened.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, createNote, getAuthState, getConversation, streamChat } from "../../shared/api-client";
import { refreshUsage, useUsage } from "../../shared/usage-store";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { extractFollowUpQuestion } from "../follow-up";
import { FollowUpIcon } from "../recent/parts";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

type SaveState = "saving" | "saved" | "failed";

/** The conversation to pick up again next time the panel opens. */
const LAST_CHAT_KEY = "generalChatId";

/** Ways to begin: each puts the start of a question in the box for the student to finish. */
const STARTERS = [
  { label: "Explain a concept step by step", begins: "Explain step by step: " },
  { label: "Quiz me on a topic", begins: "Quiz me on " },
  { label: "Plan my revision for an exam", begins: "Help me plan my revision for an exam on " },
];

export function ChatTab(): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [waking, setWaking] = useState(false);
  const [error, setError] = useState<{ message: string; limited: boolean } | null>(null);
  const [saved, setSaved] = useState<Record<string, SaveState>>({});
  const [latestUserMessageId, setLatestUserMessageId] = useState<string | null>(null);
  const usage = useUsage();
  const conversationIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastQuestionRef = useRef<string | null>(null);
  const latestUserMessageRef = useRef<HTMLLIElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    conversationIdRef.current = null;
    setMessages([]);
    setError(null);
    setSaved({});
    chrome.storage.local.remove(LAST_CHAT_KEY).catch(() => undefined);
  }, []);

  // Pick up the last chat. Only a signed-in chat can be read back from the server.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const stored = (await chrome.storage.local.get(LAST_CHAT_KEY))[LAST_CHAT_KEY] as string | undefined;
      const { sessionToken } = await getAuthState();
      if (!stored || !sessionToken) return;
      try {
        const detail = await getConversation(stored);
        if (cancelled) return;
        conversationIdRef.current = detail.id;
        setMessages(detail.messages.map((m) => ({ id: m.id, role: m.role, content: m.content })));
      } catch {
        // Expired, deleted, or another account's: start fresh.
        chrome.storage.local.remove(LAST_CHAT_KEY).catch(() => undefined);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Signing out, or switching account, clears a chat that belonged to the previous one.
  useEffect(() => {
    const onChange = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "local" || !changes.userEmail) return;
      const { oldValue, newValue } = changes.userEmail;
      if (oldValue && oldValue !== newValue) reset();
    };
    chrome.storage.onChanged.addListener(onChange);
    return () => chrome.storage.onChanged.removeListener(onChange);
  }, [reset]);

  // Escape stops an answer that is still being written.
  useEffect(() => {
    if (!streaming) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") abortRef.current?.abort();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming]);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    latestUserMessageRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }, [latestUserMessageId]);

  const ask = useCallback(
    async (question: string) => {
      if (!question || streaming) return;
      lastQuestionRef.current = question;
      setError(null);
      setStreaming(true);
      const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: question };
      const answerId = crypto.randomUUID();
      setMessages((prev) => [...prev, userMessage, { id: answerId, role: "assistant", content: "" }]);
      setLatestUserMessageId(userMessage.id);

      const abort = new AbortController();
      abortRef.current = abort;
      try {
        const request = {
          conversation_id: conversationIdRef.current,
          presentation_id: null,
          query_mode: "general",
          slide_id: null,
          object_id: null,
          message: question,
        } as const;
        for await (const event of streamChat(request, () => setWaking(true), abort.signal)) {
          if (abort.signal.aborted) break;
          setWaking(false);
          if (event.type === "delta") {
            setMessages((prev) => prev.map((m) => (m.id === answerId ? { ...m, content: m.content + event.text } : m)));
          } else if (event.type === "done") {
            conversationIdRef.current = event.data.conversation_id;
            chrome.storage.local.set({ [LAST_CHAT_KEY]: event.data.conversation_id }).catch(() => undefined);
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
        setWaking(false);
      }
    },
    [streaming]
  );

  const send = () => {
    const question = input.trim();
    if (!question) return;
    setInput("");
    void ask(question);
  };

  const save = async (answer: ChatMessage, question: string) => {
    setSaved((prev) => ({ ...prev, [answer.id]: "saving" }));
    try {
      await createNote({ title: question.slice(0, 200), body: answer.content, source: "ai" });
      setSaved((prev) => ({ ...prev, [answer.id]: "saved" }));
    } catch {
      setSaved((prev) => ({ ...prev, [answer.id]: "failed" }));
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-none items-center justify-between gap-3 border-b border-slate-100 bg-white px-4 py-4">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-800">Chat</h2>
          <p className="truncate text-sm text-slate-400">Ask anything. No slide needed.</p>
        </div>
        {messages.length > 0 && (
          <Button variant="secondary" onClick={reset} className="flex-none">
            New chat
          </Button>
        )}
      </div>

      <div className="scrollbar-thin flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm leading-relaxed text-slate-600">
              A plain chat with the tutor, for questions that are not about a slide on your screen. To ask about a
              slide, capture it in the Ask tab.
            </p>
            <ul className="flex flex-col gap-2">
              {STARTERS.map((starter) => (
                <li key={starter.label}>
                  <button
                    type="button"
                    onClick={() => {
                      setInput(starter.begins);
                      inputRef.current?.focus();
                    }}
                    className="w-full rounded-md border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 shadow-subtle transition-colors duration-[120ms] hover:bg-slate-50 active:bg-slate-100"
                  >
                    {starter.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {messages.map((message, index) => {
              if (message.role === "user") {
                return (
                  <li
                    key={message.id}
                    ref={message.id === latestUserMessageId ? latestUserMessageRef : undefined}
                    className="max-w-[90%] self-end whitespace-pre-wrap break-words rounded-md bg-indigo-600 px-3 py-2 text-sm text-white"
                  >
                    {message.content}
                  </li>
                );
              }
              const pending = !message.content && streaming;
              const followUp = pending || streaming ? null : extractFollowUpQuestion(message.content);
              const state = saved[message.id];
              return (
                <li key={message.id} className="flex min-w-0 max-w-full flex-col items-start gap-1 self-start">
                  <div className="max-w-full overflow-x-auto rounded-md border border-amber-100 bg-amber-50/70 px-3.5 py-3 dark:border-indigo-100 dark:bg-indigo-50/40 text-sm leading-relaxed text-slate-700 shadow-subtle">
                    {pending ? <span className="text-slate-400">Thinking…</span> : <MathText text={message.content} />}
                  </div>
                  {!pending && !streaming && usage?.signed_in && (
                    <button
                      type="button"
                      disabled={state === "saving" || state === "saved"}
                      onClick={() => {
                        const asked = messages.slice(0, index).reverse().find((m) => m.role === "user");
                        void save(message, asked?.content ?? "Saved answer");
                      }}
                      className="rounded-sm px-2 py-1 text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:hover:bg-transparent"
                    >
                      {state === "saved"
                        ? "Saved to notes"
                        : state === "saving"
                          ? "Saving…"
                          : state === "failed"
                            ? "Couldn't save. Try again"
                            : "Save to notes"}
                    </button>
                  )}
                  {followUp && (
                    <button
                      type="button"
                      onClick={() => void ask(followUp)}
                      className="mt-0.5 flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-left text-xs font-medium text-indigo-700 transition-colors duration-[120ms] hover:bg-indigo-100 dark:text-indigo-300"
                    >
                      <FollowUpIcon />
                      <span className="min-w-0">
                        <MathText text={followUp} />
                      </span>
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {waking && (
          <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 shadow-subtle dark:text-amber-300" role="status">
            Waking up the server. This takes about a minute after a quiet period.
          </p>
        )}

        {error?.limited && (
          <div className="rounded-md border border-violet-100 bg-violet-50/50 p-3 text-sm text-slate-600">{error.message}</div>
        )}
        {error && !error.limited && (
          <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700 shadow-subtle dark:text-red-300">
            <p className="font-medium">The answer could not be completed.</p>
            <p>{error.message}</p>
            {lastQuestionRef.current && (
              <button
                type="button"
                onClick={() => void ask(lastQuestionRef.current ?? "")}
                className="mt-2 font-medium underline underline-offset-2"
              >
                Try again
              </button>
            )}
          </div>
        )}
      </div>

      <form
        className="flex flex-none gap-2 border-t border-slate-200 bg-white px-4 py-3"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask anything"
          aria-label="Ask the tutor anything"
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
