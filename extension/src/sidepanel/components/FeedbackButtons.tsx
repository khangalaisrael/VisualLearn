/**
 * 👍/👎 under an answer: a slide's summary or a chat reply. Works signed out
 * too. A 👎 is sent at once, then offers a box to say what was wrong, so the
 * rating is kept even if the student never writes anything. Rating again
 * replaces the earlier rating rather than adding another.
 */

import { useState } from "react";

import { ApiError, sendFeedback } from "../../shared/api-client";
import { FEEDBACK_COMMENT_MAX, feedbackRequest } from "../feedback";
import type { FeedbackRating, FeedbackTarget } from "@shared/types";

type Status = "idle" | "sending" | "sent" | "failed" | "limited";

function ThumbIcon({ down, filled }: { down?: boolean; filled: boolean }): JSX.Element {
  return (
    <svg
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 ${down ? "rotate-180" : ""}`}
      fill={filled ? "currentColor" : "none"}
      aria-hidden="true"
    >
      <path
        d="M5 7.25 7.6 2.1a.9.9 0 0 1 .8-.5c.9 0 1.6.8 1.45 1.7L9.5 5.75h3.1a1.4 1.4 0 0 1 1.37 1.7l-1.1 5a1.4 1.4 0 0 1-1.37 1.1H5zM5 7.25H2.75v6.3H5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const buttonClass =
  "flex h-6 w-6 items-center justify-center rounded-sm text-slate-400 transition-colors duration-[120ms] hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50 disabled:hover:bg-transparent";

export function FeedbackButtons({
  target,
  answerId,
}: {
  target: FeedbackTarget;
  /** The slide id for a summary, the server's message id for a chat reply. */
  answerId: string;
}): JSX.Element {
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [feedbackId, setFeedbackId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [commentOpen, setCommentOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [commentSent, setCommentSent] = useState(false);

  const send = async (next: FeedbackRating, withComment?: string): Promise<boolean> => {
    setStatus("sending");
    try {
      const saved = await sendFeedback(
        feedbackRequest({ target, answerId, rating: next, comment: withComment, feedbackId })
      );
      setFeedbackId(saved.id);
      setRating(next);
      setStatus("sent");
      return true;
    } catch (error) {
      setStatus(error instanceof ApiError && error.status === 429 ? "limited" : "failed");
      return false;
    }
  };

  const rate = async (next: FeedbackRating) => {
    if (next === rating || status === "sending") return;
    setCommentSent(false);
    setCommentOpen(next === "down");
    await send(next);
  };

  const submitComment = async () => {
    if (!comment.trim()) return;
    if (await send("down", comment)) {
      setCommentOpen(false);
      setCommentSent(true);
    }
  };

  const message =
    status === "limited"
      ? "You've sent a lot of feedback today, thank you!"
      : status === "failed"
        ? "Couldn't send that. Try again"
        : commentSent
          ? "Thanks, that helps."
          : status === "sent" && rating === "up"
            ? "Thanks!"
            : null;

  return (
    <div className="flex w-full max-w-full flex-col gap-1.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          aria-label="Good answer"
          aria-pressed={rating === "up"}
          title="Good answer"
          disabled={status === "sending"}
          onClick={() => void rate("up")}
          className={`${buttonClass} ${rating === "up" ? "text-indigo-600 dark:text-indigo-300" : ""}`}
        >
          <ThumbIcon filled={rating === "up"} />
        </button>
        <button
          type="button"
          aria-label="Bad answer"
          aria-pressed={rating === "down"}
          title="Bad answer"
          disabled={status === "sending"}
          onClick={() => void rate("down")}
          className={`${buttonClass} ${rating === "down" ? "text-indigo-600 dark:text-indigo-300" : ""}`}
        >
          <ThumbIcon down filled={rating === "down"} />
        </button>
        {message && (
          <span className="ml-1 text-xs text-slate-400" role="status">
            {message}
          </span>
        )}
      </div>
      {commentOpen && rating === "down" && (
        <form
          className="flex w-full gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submitComment();
          }}
        >
          <input
            type="text"
            value={comment}
            maxLength={FEEDBACK_COMMENT_MAX}
            onChange={(event) => setComment(event.target.value)}
            placeholder="What was wrong? (optional)"
            aria-label="What was wrong with this answer? (optional)"
            className="min-w-0 flex-1 rounded-sm border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 transition-colors duration-[120ms] placeholder:text-slate-400 focus:border-indigo-400"
          />
          <button
            type="submit"
            disabled={!comment.trim() || status === "sending"}
            className="rounded-sm px-2 py-1 text-xs font-medium text-indigo-600 transition-colors duration-[120ms] hover:bg-indigo-50 disabled:opacity-50 disabled:hover:bg-transparent dark:text-indigo-300"
          >
            Send
          </button>
          <button
            type="button"
            onClick={() => setCommentOpen(false)}
            className="rounded-sm px-2 py-1 text-xs font-medium text-slate-500 transition-colors duration-[120ms] hover:bg-slate-100"
          >
            Skip
          </button>
        </form>
      )}
    </div>
  );
}
