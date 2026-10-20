import { describe, expect, it } from "vitest";

import { FEEDBACK_COMMENT_MAX, feedbackRequest } from "./feedback";

describe("feedbackRequest", () => {
  it("rates a summary by its slide and a chat reply by its message", () => {
    expect(feedbackRequest({ target: "summary", answerId: "s1", rating: "up" })).toEqual({
      target: "summary",
      slide_id: "s1",
      rating: "up",
    });
    expect(feedbackRequest({ target: "chat", answerId: "m1", rating: "down" })).toEqual({
      target: "chat",
      message_id: "m1",
      rating: "down",
    });
  });

  it("sends a trimmed comment with a thumbs down only", () => {
    expect(feedbackRequest({ target: "chat", answerId: "m1", rating: "down", comment: "  wrong sign  " }).comment).toBe(
      "wrong sign"
    );
    expect(feedbackRequest({ target: "chat", answerId: "m1", rating: "down", comment: "   " })).not.toHaveProperty(
      "comment"
    );
    expect(feedbackRequest({ target: "chat", answerId: "m1", rating: "up", comment: "great" })).not.toHaveProperty(
      "comment"
    );
  });

  it("cuts a comment to what the server accepts", () => {
    const long = "x".repeat(FEEDBACK_COMMENT_MAX + 50);
    expect(feedbackRequest({ target: "summary", answerId: "s1", rating: "down", comment: long }).comment).toHaveLength(
      FEEDBACK_COMMENT_MAX
    );
  });

  it("names the earlier rating so a change replaces it", () => {
    expect(feedbackRequest({ target: "summary", answerId: "s1", rating: "down", feedbackId: "f1" }).feedback_id).toBe(
      "f1"
    );
    expect(feedbackRequest({ target: "summary", answerId: "s1", rating: "down", feedbackId: null })).not.toHaveProperty(
      "feedback_id"
    );
  });
});
