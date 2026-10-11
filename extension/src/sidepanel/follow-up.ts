/**
 * Best-effort pull of a follow-up question out of the model's answer, so it
 * can be offered as a one-click button instead of the student re-typing it.
 * The chat prompts ask the model to end with a natural follow-up question,
 * but answers vary: a labelled section, a quoted question, or just a last
 * sentence ending in "?". Three steps, each weaker than the last:
 *   1. A "Suggested follow-up" heading (the older prompts' fixed section).
 *   2. Any looser "follow-up ...:" lead-in.
 *   3. The last quoted "...?", or else the last sentence that ends in "?".
 *
 * Everything here is aware of math: a period, colon or question mark inside
 * $...$ (as in "$\lambda x. x$" or "$M[x := N]$") is part of a formula, not
 * the end of a sentence or of a lead-in. Cutting there used to produce
 * buttons like "b)$ yourself?". Returns null rather than a broken question.
 */

const MAX_QUESTION_CHARS = 240;

/** For each position in `text` (and one past the end): is it inside math? */
function mathMask(text: string): boolean[] {
  const inside: boolean[] = new Array(text.length + 1);
  let open: "$" | "$$" | "\\(" | "\\[" | null = null;
  let i = 0;
  while (i < text.length) {
    const two = text.slice(i, i + 2);
    let width = 1;
    if (open === null) {
      if (two === "$$" || two === "\\(" || two === "\\[") {
        open = two;
        width = 2;
      } else if (text[i] === "$" && text[i - 1] !== "\\") {
        open = "$";
      }
      // An opening delimiter is itself counted as outside, its body as inside.
      inside[i] = false;
      if (width === 2) inside[i + 1] = false;
    } else {
      const closes =
        (open === "$$" && two === "$$") ||
        (open === "\\(" && two === "\\)") ||
        (open === "\\[" && two === "\\]") ||
        (open === "$" && text[i] === "$" && text[i - 1] !== "\\");
      inside[i] = true;
      if (closes) {
        width = open === "$" ? 1 : 2;
        if (width === 2) inside[i + 1] = true;
        open = null;
      }
    }
    i += width;
  }
  inside[text.length] = open !== null;
  return inside;
}

/** A usable question: not empty, not enormous, with no formula left half open
 * and no LaTeX command sitting outside a formula (it would show as "\\Omega"). */
function clean(question: string): string | null {
  const trimmed = question.trim();
  if (trimmed.length < 4 || trimmed.length > MAX_QUESTION_CHARS) return null;
  const inside = mathMask(trimmed);
  if (inside[trimmed.length]) return null;
  for (const command of trimmed.matchAll(/\\[a-zA-Z]+/g)) {
    if (!inside[command.index ?? 0]) return null;
  }
  return trimmed;
}

/** Drops a lead-in clause ("A good next question might be: ..."): everything
 * up to the last colon that is followed by a space and is not in a formula. */
function dropLeadIn(question: string): string {
  const inside = mathMask(question);
  for (let i = question.length - 2; i >= 0; i--) {
    if (question[i] === ":" && /\s/.test(question[i + 1]) && !inside[i]) return question.slice(i + 1);
  }
  return question;
}

/** The first question in `text`: from its start to the first "?" outside math. */
function firstQuestion(text: string): string | null {
  const inside = mathMask(text);
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "?" && !inside[i]) return text.slice(0, i + 1);
  }
  return null;
}

/** The last sentence of `text` that ends in "?", found without splitting inside math. */
function lastQuestion(text: string): string | null {
  const inside = mathMask(text);
  let end = -1;
  for (let i = text.length - 1; i >= 0; i--) {
    if (text[i] === "?" && !inside[i]) {
      end = i;
      break;
    }
  }
  if (end === -1) return null;
  let start = 0;
  for (let i = end - 1; i > 0; i--) {
    const sentenceBreak = text[i] === "\n" || (/[.!?]/.test(text[i - 1]) && /\s/.test(text[i]));
    if (sentenceBreak && !inside[i]) {
      start = i + 1;
      break;
    }
  }
  return text.slice(start, end + 1);
}

/** A follow-up from the tail of a "Suggested follow-up: ..." style section. */
function fromTail(tail: string): string | null {
  const quoted = /["“]([^"”]+?)["”]/.exec(tail);
  if (quoted) return clean(quoted[1]);
  const question = firstQuestion(tail);
  return question ? clean(dropLeadIn(question)) : null;
}

export function extractFollowUpQuestion(text: string): string | null {
  const strictHeading = /5\.\s*\*\*Suggested follow-up\*\*\s*[—:-]?\s*([\s\S]*)$/i.exec(text);
  if (strictHeading) {
    const found = fromTail(strictHeading[1].trim());
    if (found) return found;
  }

  const looseHeading = /(?:suggested\s+)?follow-?up[^:]{0,40}:\s*([\s\S]*)$/i.exec(text);
  if (looseHeading) {
    const found = fromTail(looseHeading[1].trim());
    if (found) return found;
  }

  const lastQuoted = [...text.matchAll(/["“]([^"”]{4,}?\?)["”]/g)].pop();
  if (lastQuoted) {
    const found = clean(lastQuoted[1]);
    if (found) return found;
  }

  const question = lastQuestion(text);
  return question ? clean(dropLeadIn(question)) : null;
}
