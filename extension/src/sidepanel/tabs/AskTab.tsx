/**
 * Ask tab — capture the current slide, inspect what VisionLearn extracted
 * from it, and chat about it. Milestone 3 (see docs/ROADMAP.md) wires the
 * chat box below the capture result to POST /chat in "slide" query mode,
 * grounded on every object detected on the captured slide. "Figure" mode
 * (grounded on a single selected object) needs the overlay renderer, which
 * doesn't exist yet, so there is no object picker here.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { streamChat } from "../../shared/api-client";
import type {
  CaptureRequestMessage,
  SlideAnalysisFailedMessage,
  SlideAnalyzedMessage,
} from "../../service-worker/messages";
import { Button } from "../components/Button";
import { MathText } from "../components/MathText";
import { ObjectCard } from "../components/ObjectCard";
import { ObjectCardSkeleton } from "../components/ObjectCardSkeleton";

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; result: SlideAnalyzedMessage["result"] }
  | { status: "error"; message: string };

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

const PRESET_QUESTIONS = ["Explain this slide", "Summarize", "Give an example", "Simplify"];

/** Extracts a follow-up question from the tail of a "5. Suggested
 * follow-up — ..." style section: a quoted "...?" if present, else the
 * text up to the first "?" (trimmed after the last ":" if any). */
function extractFromTail(tail: string): string | null {
  const quoted = /["“]([^"”]+?)["”]/.exec(tail);
  if (quoted) return quoted[1].trim();

  const qMarkIndex = tail.indexOf("?");
  if (qMarkIndex === -1) return null;
  const upToQuestion = tail.slice(0, qMarkIndex + 1);
  const colonIndex = upToQuestion.lastIndexOf(":");
  return (colonIndex !== -1 ? upToQuestion.slice(colonIndex + 1) : upToQuestion).trim();
}

/**
 * Best-effort pull of a follow-up question out of the model's answer so
 * it can be offered as a one-click button instead of the student
 * re-typing it. `chat_slide.v3.md`/`chat_figure.v3.md` ask for a fixed
 * "5. **Suggested follow-up**" section, but free-text answers don't
 * always comply (short/casual answers especially) — different wording,
 * no bold, no numbering, or no heading at all. Three-step fallback, each
 * strictly weaker than the last, so a button still shows up whenever the
 * answer plausibly contains a follow-up question:
 *   1. The exact heading the prompt asks for.
 *   2. Any looser "(suggest|follow-up|next question)... :" style lead-in,
 *      anywhere in the text, not just as a numbered heading.
 *   3. The last quoted "...?" or the last "?"-terminated sentence in the
 *      whole message, if nothing else matched — the model asked *some*
 *      question even if it didn't label it as a suggestion.
 * Returns null only when none of these find anything, rather than
 * guessing wrong.
 */
function extractFollowUpQuestion(text: string): string | null {
  const strictHeading = /5\.\s*\*\*Suggested follow-up\*\*\s*[—:-]?\s*([\s\S]*)$/i.exec(text);
  if (strictHeading) {
    const found = extractFromTail(strictHeading[1].trim());
    if (found) return found;
  }

  const looseHeading = /(?:suggested\s+)?follow-?up[^:]{0,40}:\s*([\s\S]*)$/i.exec(text);
  if (looseHeading) {
    const found = extractFromTail(looseHeading[1].trim());
    if (found) return found;
  }

  const lastQuoted = [...text.matchAll(/["“]([^"”]{4,}?\?)["”]/g)].pop();
  if (lastQuoted) return lastQuoted[1].trim();

  const sentences = text.split(/(?<=[.!?])\s+/).map((s) => s.trim());
  const lastQuestion = [...sentences].reverse().find((s) => s.endsWith("?"));
  if (!lastQuestion) return null;

  // Trim a leading lead-in clause ("A good next question might be: ...")
  // that the sentence-split fallback can't otherwise strip.
  const colonIndex = lastQuestion.lastIndexOf(":");
  return colonIndex !== -1 ? lastQuestion.slice(colonIndex + 1).trim() : lastQuestion;
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function TypingIndicator(): JSX.Element {
  return (
    <span className="inline-flex items-center gap-1" aria-label="VisionLearn is typing">
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" style={{ animationDelay: "200ms" }} />
      <span className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400" style={{ animationDelay: "400ms" }} />
    </span>
  );
}

function Avatar({ role }: { role: ChatMessage["role"] }): JSX.Element {
  return role === "user" ? (
    <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-indigo-600 text-[11px] font-medium text-white">
      You
    </span>
  ) : (
    <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full border border-slate-300 bg-white text-[11px] font-medium text-indigo-600">
      VL
    </span>
  );
}

export function AskTab(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const lastQuestionRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const listener = (message: SlideAnalyzedMessage | SlideAnalysisFailedMessage) => {
      if (message.type === "SLIDE_ANALYZED") {
        setState({ status: "loaded", result: message.result });
        setMessages([]);
        conversationIdRef.current = null;
      } else if (message.type === "SLIDE_ANALYSIS_FAILED") {
        setState({ status: "error", message: message.message });
      }
      return false;
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const captureNow = useCallback(() => {
    setState({ status: "loading" });
    const message: CaptureRequestMessage = {
      type: "CAPTURE_REQUEST",
      presentationId: null,
      slideNumber: 1,
    };
    chrome.runtime.sendMessage(message).catch((error) => {
      setState({ status: "error", message: String(error) });
    });
  }, []);

  const askQuestion = useCallback(
    async (question: string) => {
      if (state.status !== "loaded" || !question || isStreaming) {
        return;
      }
      const { presentation_id, slide_id } = state.result;
      lastQuestionRef.current = question;
      setChatError(null);
      setIsStreaming(true);

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: question,
        timestamp: Date.now(),
      };
      const assistantMessageId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        userMessage,
        { id: assistantMessageId, role: "assistant", content: "", timestamp: Date.now() },
      ]);

      try {
        for await (const event of streamChat({
          conversation_id: conversationIdRef.current,
          presentation_id,
          query_mode: "slide",
          slide_id,
          object_id: null,
          message: question,
        })) {
          if (event.type === "delta") {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantMessageId ? { ...m, content: m.content + event.text } : m))
            );
          } else if (event.type === "done") {
            conversationIdRef.current = event.data.conversation_id;
          } else if (event.type === "error") {
            setChatError(event.data.message);
          }
        }
      } catch (error) {
        setChatError(error instanceof Error ? error.message : String(error));
      } finally {
        setIsStreaming(false);
      }
    },
    [state, isStreaming]
  );

  const sendChatMessage = useCallback(async () => {
    const question = chatInput.trim();
    if (!question) return;
    setChatInput("");
    await askQuestion(question);
  }, [chatInput, askQuestion]);

  const retryLastQuestion = useCallback(() => {
    if (lastQuestionRef.current) {
      void askQuestion(lastQuestionRef.current);
    }
  }, [askQuestion]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isStreaming]);

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <p className="text-sm text-slate-500">
        Capture the current slide to see what VisionLearn extracted from it.
      </p>

      <div className="sticky top-0 z-10 -mx-4 border-b border-indigo-100 bg-white px-4 py-2 shadow-subtle">
        <Button onClick={captureNow} disabled={state.status === "loading"}>
          {state.status === "loading" ? "Analyzing…" : "Capture Current Slide"}
        </Button>
      </div>

      {state.status === "loading" && (
        <ul className="flex flex-col gap-3">
          <ObjectCardSkeleton />
          <ObjectCardSkeleton />
        </ul>
      )}

      {state.status === "error" && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 shadow-subtle">
          <p className="font-medium">Something went wrong.</p>
          <p>{state.message}</p>
        </div>
      )}

      {state.status === "loaded" && (
        <div className="flex flex-col gap-3">
          <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">{state.result.summary}</p>
          {state.result.objects.length === 0 && (
            <p className="text-sm text-slate-400">No objects detected on this slide.</p>
          )}
          <ul className="flex flex-col gap-3">
            {state.result.objects.map((object) => (
              <ObjectCard key={object.id} object={object} />
            ))}
          </ul>
        </div>
      )}

      {state.status === "loaded" && (
        <div className="flex flex-1 flex-col gap-3 border-t border-slate-200 pt-4">
          <p className="text-sm font-medium text-slate-700">Ask about this slide</p>

          <div className="flex flex-wrap gap-2">
            {PRESET_QUESTIONS.map((question) => (
              <button
                key={question}
                type="button"
                disabled={isStreaming}
                onClick={() => void askQuestion(question)}
                className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 transition-colors duration-[120ms] hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </div>

          {messages.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-center text-sm text-slate-400">
              Ask a question about this slide to get started.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {messages.map((message) => {
                const isPendingAssistant = !message.content && isStreaming && message.role === "assistant";
                const followUpQuestion =
                  message.role === "assistant" && !isPendingAssistant
                    ? extractFollowUpQuestion(message.content)
                    : null;
                return (
                  <li
                    key={message.id}
                    className={`flex max-w-[90%] flex-col gap-1 ${
                      message.role === "user" ? "self-end items-end" : "self-start items-start"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {message.role === "assistant" && <Avatar role={message.role} />}
                      <span className="text-xs text-slate-400">
                        {message.role === "user" ? "You" : "VisionLearn"} · {formatTime(message.timestamp)}
                      </span>
                      {message.role === "user" && <Avatar role={message.role} />}
                    </div>
                    <div
                      className={
                        message.role === "user"
                          ? "rounded-md bg-indigo-600 px-3 py-2 text-sm text-white"
                          : "rounded-md border border-indigo-100 bg-indigo-50/40 px-3.5 py-3 text-sm leading-relaxed text-slate-700 shadow-subtle"
                      }
                    >
                      {isPendingAssistant ? <TypingIndicator /> : <MathText text={message.content} />}
                    </div>
                    {followUpQuestion && (
                      <button
                        type="button"
                        disabled={isStreaming}
                        onClick={() => void askQuestion(followUpQuestion)}
                        className="mt-0.5 flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-left text-xs font-medium text-indigo-700 transition-colors duration-[120ms] hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <span aria-hidden="true">↳</span>
                        {followUpQuestion}
                      </button>
                    )}
                  </li>
                );
              })}
              <div ref={messagesEndRef} />
            </ul>
          )}

          {chatError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 shadow-subtle">
              <p className="font-medium">Something went wrong.</p>
              <p>{chatError}</p>
              <button
                type="button"
                onClick={retryLastQuestion}
                className="mt-2 text-sm font-medium text-red-700 underline decoration-red-300 underline-offset-2 hover:text-red-800"
              >
                Retry
              </button>
            </div>
          )}

          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void sendChatMessage();
            }}
          >
            <input
              type="text"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Ask a question about this slide…"
              disabled={isStreaming}
              className="flex-1 rounded-sm border border-slate-300 px-3 py-2 text-sm transition-colors duration-[120ms] focus:border-indigo-400 disabled:opacity-50"
            />
            <Button type="submit" disabled={isStreaming || !chatInput.trim()}>
              Send
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
