# VisionLearn brand guide

One page, so every screen, post and email looks and sounds like the same product.

## Positioning

**For** STEM students who study from lecture slides, **VisionLearn** is the study partner that reads
the slide on your screen and explains it, then turns what you captured into quizzes, guides,
flashcards and runnable code. **Unlike** tools that start from an upload or a blank page, it starts from
what you are already looking at, and it reads nothing until you press Capture.

Where it sits among study tools: flashcard apps (Quizlet, Anki) start from cards you make; AI tutors
(StudyFetch, Knowt) start from files you upload; VisionLearn starts from the slide on your screen and is
built for equations, diagrams and code.

## Brand idea: "the frame"

The logo is a **V seen through capture-frame corners**. That is the product: you frame a slide, and
it becomes clear. Reuse the idea, not just the logo:

- **The frame**: yellow corner brackets around the thing being captured or explained.
- **The highlighter**: a soft yellow swipe behind the one phrase that matters (the headline's
  "lecture slide"). One highlight per screen, never more.

## Tagline

**See the slide. Get it.**

Short forms: "Understand any lecture slide." (headline) and "Study from what's on your screen."
(supporting line).

## Personality

Clear, calm, sharp, honest. A good teaching assistant, not a cheerleader. No gamification, no
confetti, no "supercharge your learning".

| We say | We don't say |
|---|---|
| "Press Capture, then ask." | "Unlock the power of AI-driven learning!" |
| "It reads nothing until you press Capture." | "Your privacy is our top priority." |
| "Halving the list gives log n levels." (a real explanation) | "Great question! Let's dive in!" |
| "20 captures a day, so it stays free." | "Unlimited*" |

Rules: short sentences; say what it does, then show it; give real numbers; label examples as
examples; never claim something the product doesn't do.

## Name

**VisionLearn AI** is the product name (extension, site, docs). Write it as one word with a capital
L. The GitHub repository is called `VisualLearn`; renaming it to `VisionLearn` would remove the mismatch.

## Colour

| Role | Name | Hex | Use |
|---|---|---|---|
| Primary | Deep indigo | `#2E2A8A` | Logo tile, buttons, key text accents |
| UI accent | Indigo | `#3B36B8` | Links, labels, small accents |
| Soft | Lilac | `#C7D2FE` | Logo corners, tints, dark-mode accent |
| Signal | Highlighter | `#FCD34D` | The one highlight and the capture frame; never for body text |
| Text | Ink | `#0F172A` | Body and headings (light mode) |

Dark mode: ink background `#0A0D1A`, lilac accents, and the highlighter yellow for the primary button.
Amber is the brand's only warm colour; keep it rare so it keeps meaning "this is the important part".

## Logo

`extension/public/icons/logo.svg`: indigo tile, lilac frame corners, amber V.

- Minimum size 16px (it reads as a V in a tile). Use the tile, not the bare V, on busy backgrounds.
- Keep clear space of a quarter of the tile's width.
- Wordmark: "Vision" in the text colour and "Learn" in indigo, set in bold with slightly tight tracking.
- One-colour use: all-white or all-indigo tile, with the V cut out.
- Don't stretch, recolour the V, add shadows or put it on a gradient.

## Type

System sans-serif stack (no web fonts, so pages stay one fast request): headings bold to extra-bold
with tight tracking (about -0.03em); body regular at 16px with a 1.65 line height. Code in the
system monospace.

## Where this is applied

- Landing page (`backend/app/api/landing.py`): palette, highlighter headline, capture-frame on the example.
- Not yet applied: the extension's side panel UI, the Chrome Web Store listing, social images. Start
  with the side panel colours so the product and the site match.
