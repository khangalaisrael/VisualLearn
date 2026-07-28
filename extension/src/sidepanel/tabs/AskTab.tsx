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
}

export function AskTab(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);

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

  const sendChatMessage = useCallback(async () => {
    if (state.status !== "loaded" || !chatInput.trim() || isStreaming) {
      return;
    }
    const { presentation_id, slide_id } = state.result;
    const question = chatInput.trim();
    setChatInput("");
    setChatError(null);
    setIsStreaming(true);

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: question };
    const assistantMessageId = crypto.randomUUID();
    setMessages((prev) => [...prev, userMessage, { id: assistantMessageId, role: "assistant", content: "" }]);

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
  }, [state, chatInput, isStreaming]);

  return (
    <div className="scrollbar-thin flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <p className="text-sm text-slate-500">
        Capture the current slide to see what VisionLearn extracted from it.
      </p>

      <Button onClick={captureNow} disabled={state.status === "loading"}>
        {state.status === "loading" ? "Analyzing…" : "Capture Current Slide"}
      </Button>

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

          <ul className="flex flex-col gap-2">
            {messages.map((message) => (
              <li
                key={message.id}
                className={
                  message.role === "user"
                    ? "max-w-[85%] self-end rounded-md bg-indigo-600 px-3 py-2 text-sm text-white"
                    : "max-w-[85%] self-start whitespace-pre-wrap rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700 shadow-subtle"
                }
              >
                {message.content ? (
                  <MathText text={message.content} />
                ) : isStreaming && message.role === "assistant" ? (
                  "…"
                ) : (
                  ""
                )}
              </li>
            ))}
          </ul>

          {chatError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 shadow-subtle">{chatError}</div>
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
