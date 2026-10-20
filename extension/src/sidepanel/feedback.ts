/**
 * Building the request behind the 👍/👎 under an answer (components/FeedbackButtons.tsx).
 */

import type { FeedbackCreateRequest, FeedbackRating, FeedbackTarget } from "@shared/types";

/** The server refuses a longer comment; the box stops at this length too. */
export const FEEDBACK_COMMENT_MAX = 1000;

export interface FeedbackDraft {
  target: FeedbackTarget;
  /** The slide id for a summary, the server's message id for a chat reply. */
  answerId: string;
  rating: FeedbackRating;
  comment?: string;
  /** The id the previous rating of this answer came back with. */
  feedbackId?: string | null;
}

export function feedbackRequest(draft: FeedbackDraft): FeedbackCreateRequest {
  const comment = draft.comment?.trim().slice(0, FEEDBACK_COMMENT_MAX);
  return {
    target: draft.target,
    ...(draft.target === "summary" ? { slide_id: draft.answerId } : { message_id: draft.answerId }),
    rating: draft.rating,
    // A 👍 carries no comment: the box is only offered after a 👎.
    ...(draft.rating === "down" && comment ? { comment } : {}),
    ...(draft.feedbackId ? { feedback_id: draft.feedbackId } : {}),
  };
}
