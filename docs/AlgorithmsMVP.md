# Theory of Algorithms — MVP Scope

This is a phased scope for [TheoryOfAlgorithm.md](./TheoryOfAlgorithm.md). That document is the north star; it stays as-is. This file exists to answer the question it doesn't: **what do we actually build first**.

Ordering principle: ship the highest-value reasoning (complexity + recurrences, in text) through the *existing* chat pipeline before touching visualization, structured-representation storage, or multi-stage pipelines. Every phase must be independently shippable and demoable.

---

## Phase 1 — Complexity & Recurrence Reasoning (text only)

**Goal:** a student can ask "why is this O(n log n)?" or "solve this recurrence" about the current slide and get a correct, step-shown answer — no new infra, no visualization.

**In scope (doc sections):**
- §2 Mathematical Understanding (don't trust OCR blindly, state interpretation of ambiguous notation)
- §3 Complexity Analysis Engine (explain *why*, not just the label)
- §4 Loop Analysis, §5 Non-Standard Loops, §6 Sequential Operations, §7 Conditional Complexity
- §8 Recurrence Relations (substitution, Master Theorem, iteration — text reasoning only, no tree diagram)
- §10 Master Theorem
- §21 Asymptotic Notation (O/Θ/Ω distinctions)
- §23 Common Student Errors (a short, hardcoded list of the 5 examples already in the doc, injected into the prompt as few-shot corrections)
- §28/§29 Verification — **scoped down**, see "Verification for MVP" below
- §35 Grounding, §36 Error Handling (already partially covered by existing `analysis`/`chat` prompt conventions — extend, don't rebuild)

**Explicitly deferred to later phases:** §9 Recursion Trees (visual), §12 Algorithm Tracing, §13/§14 Graph Algorithms, §15/§16 Sorting/Searching catalog, §17–20 D&C/DP/Greedy/Correctness proofs, §24 Explanation Modes (ship one tone first), §30–32 Visualization + structured JSON storage, §33 dedicated pipeline architecture.

**Integration point:** Do not build a new pipeline or endpoint. Add a new `query_mode: "algorithm"` (or extend `slide` mode's prompt with algorithm-aware instructions if the slide is classified as algorithmic) to the existing `/chat` endpoint, following the same versioned-prompt convention already in use (`chat_slide.v5.md` → add `chat_algorithm.v1.md`). This reuses `backend/app/core/prompt_loader.py` and the existing SSE streaming path unchanged.

**Verification for MVP:** Full symbolic verification (§28/§29 as written) is out of scope for Phase 1 — it requires either a symbolic math library integration or a second verification model call, both non-trivial. Instead: a single "show your work" prompting requirement (the model must state loop counts / recurrence parameters / dominant term explicitly before concluding) plus one lightweight self-check line appended to the prompt ("Before answering, re-derive the result once more and confirm it matches"). This is a real regression risk to accept, not a solved problem — flag it as a known gap, revisit with real symbolic verification (e.g. sympy-backed recurrence solving) in Phase 2 once there's usage data on how often the model gets these wrong.

**Deliverable:** one new prompt file, one new/extended query_mode branch in `backend/app/api/v1/chat.py`, and a short eval set (10–15 hand-picked algorithms-slide questions with known-correct answers) to catch regressions before shipping.

---

## Phase 2 — Structured Representation + Recursion Trees

**Goal:** the system produces a structured JSON representation of the algorithm/recurrence on the slide (extending the existing `SlideObject` schema pattern from `analysis.v4`), and can render an ASCII/simple recursion tree in the response.

**In scope:** §1 structured classification (recurrence/algorithm sub-types), §9 Recursion Trees (text/ASCII form first, not a rendered diagram), §11 Recursion Analysis, §32 Structured Internal Representation, real symbolic verification for algebra/recurrence-parameter checks (closing the Phase 1 gap).

**Deferred:** rendered/interactive visualization (needs frontend diagram infra — doesn't exist yet), algorithm tracing, graph algorithms.

---

## Phase 3 — Algorithm Tracing & Sorting/Searching Catalog

**Goal:** trace concrete algorithms step-by-step (§12), cover the standard sorting/searching catalog with comparisons (§15/§16).

## Phase 4 — Graphs, DP, Greedy, Proofs

§13/§14 graph algorithms, §17–20 (D&C formalized, DP, greedy, correctness proofs). This is where the doc's full breadth starts mattering; by this point there should be real usage data guiding which of these actually gets asked about.

## Phase 5 — Visualization Engine & Explanation Modes

§24 (Simple/University/Rigorous/Exam/Socratic — start with University as default, add modes based on demand), §30/§31 (rendered recursion trees, DP tables, graph traversal animations — requires new frontend charting/diagram components), §38 (contextual action surfacing in the UI).

---

## What this file is not
Not a commitment to build all 5 phases — later phases should be re-scoped based on what Phase 1 usage actually shows students asking for. The only firm commitment here is Phase 1, sized to ship without new infrastructure.
