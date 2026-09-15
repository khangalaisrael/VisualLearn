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

**Shipped (2026-09-15) — the recurrence-verification slice**: `backend/app/services/recurrence_solver.py` deterministically parses a slide object's `latex`/`extracted_text` for the standard `T(n) = a·T(n/b) + f(n)` shape (regex, not the VLM or chat model), then computes the exact Master Theorem case, resulting Θ-complexity, and an ASCII recursion tree with `sympy` — independent of anything the chat model says. `algorithm`-mode chat (`_build_algorithm_context` in `backend/app/api/v1/chat.py`) runs this over every object on the slide and injects any verified result into the context as ground truth; `prompts/chat_algorithm.v2.md` instructs the model to explain around it rather than re-derive it from scratch. Deliberately narrow: only single-recursive-term recurrences with numeric `a`/`b` and `f(n)` in `{1, n^p, log(n), sqrt(n), n^p·log(n)}` are recognized — anything else (multiple recursive terms, non-numeric coefficients, exponential `f(n)`) returns `master_case: "inconclusive"` rather than a guess, and the model is told to fall back to deriving it itself. Verified against known textbook recurrences (merge sort, binary search, Karatsuba, Strassen) in `tests/backend/test_recurrence_solver.py`, and end-to-end against the real Docker stack with a VLM-extracted slide.

**Not yet shipped from Phase 2**: no persisted structured representation on `SlideObject` itself (the analysis is computed on-the-fly per algorithm-mode chat request, not stored at slide-analyze time — lower risk, but means it isn't available to any other consumer, e.g. a future "Recurrence detected → Solve" UI action from §38), no rendered/interactive recursion tree (ASCII only), no algorithm tracing, no non-recurrence structured representation (loops, DP, graphs still rely entirely on the chat model's own reasoning, unverified).

**Deferred:** rendered/interactive visualization (needs frontend diagram infra — doesn't exist yet), algorithm tracing, graph algorithms.

---

## Phase 3 — Algorithm Tracing & Sorting/Searching Catalog

**Goal:** trace concrete algorithms step-by-step (§12), cover the standard sorting/searching catalog with comparisons (§15/§16).

**Shipped (2026-09-15) — the tracing slice**: `backend/app/services/algorithm_tracer.py` runs real, instrumented reference implementations of the six standard sorts (bubble, insertion, selection, merge, quick, heap) and both searches (linear, binary) — an execution trace by actually executing the algorithm, not the model narrating one from memory. `_build_trace_block` in `backend/app/api/v1/chat.py` detects a catalog algorithm name and an input array by keyword/regex match against the student's message and the slide's extracted text, runs the trace, and injects it into `algorithm`-mode context as ground truth (`prompts/chat_algorithm.v3.md`). Binary search on an unsorted array deliberately returns no trace rather than one that pretends the precondition holds (docs/TheoryOfAlgorithm.md §23's "binary search works on any array" misconception). Verified with 23 unit tests (`tests/backend/test_algorithm_tracer.py`, sorts checked against Python's own `sorted()`) plus end-to-end against the live Docker stack — the model reproduced the verified trace for insertion sort on `[5, 2, 4, 6, 1, 3]` exactly.

**Not yet shipped from Phase 3**: no comparative complexity/stability/in-place summary across the catalog (§15's "for each algorithm: best/average/worst case, stable?, in-place?" table), no detection from the slide's *code* specifically (only its extracted text/summary — a slide with recognizable code but no matching keyword phrase like "insertion sort" won't trigger a trace), no tracing of algorithms outside this fixed catalog (recursive algorithms like binary search's recursive form, arbitrary student-written pseudocode).

## Phase 4 — Graphs, DP, Greedy, Proofs

§13/§14 graph algorithms, §17–20 (D&C formalized, DP, greedy, correctness proofs). This is where the doc's full breadth starts mattering; by this point there should be real usage data guiding which of these actually gets asked about.

**Shipped (2026-09-15) — the graph-traversal slice**: `backend/app/services/graph_algorithm_tracer.py` runs BFS/DFS over a slide's `GraphStructure`, which the backend already extracts at analyze time via the hybrid VLM + computer-vision pipeline (`graph_topology.py`, ADR-010) — no new detection needed for the graph itself, only for which traversal the student is asking for (keyword match) and which start node (named, or defaulted to the slide's first node with that default called out explicitly). Edge `direction` (`a_to_b`/`b_to_a`/`bidirectional`/`undirected`) is respected exactly. `_format_object` in `chat.py` was also extended to surface `graph_nodes`/`graph_edges` in every mode's context (not just "algorithm") — previously the chat model never saw the actual extracted graph structure at all, only whatever text the VLM separately wrote in `summary`, a real pre-existing gap this closed as a side effect. Verified with 15 unit tests and end-to-end against the live Docker stack with a real hand-drawn graph image — including a case where the VLM's own extraction missed 2 of 5 edges, where the traversal correctly ran on the graph as actually extracted rather than the one intended, with no fabrication.

**Not yet shipped from Phase 4**: DFS/BFS only (no Dijkstra, Bellman-Ford, Floyd-Warshall, Kruskal, Prim, or topological sort — §13's fuller catalog), no dynamic programming, greedy-algorithm, or correctness-proof support at all (§17–20 remain entirely unverified, resting solely on the chat model's own reasoning like Phase 1). This phase intentionally stopped at graphs rather than attempting the full breadth — per this doc's own principle, DP/greedy/proofs should wait for real usage data on what students actually ask before committing scope to them.

## Phase 5 — Visualization Engine & Explanation Modes

§24 (Simple/University/Rigorous/Exam/Socratic — start with University as default, add modes based on demand), §30/§31 (rendered recursion trees, DP tables, graph traversal animations — requires new frontend charting/diagram components), §38 (contextual action surfacing in the UI).

---

## What this file is not
Not a commitment to build all 5 phases — later phases should be re-scoped based on what Phase 1 usage actually shows students asking for. The only firm commitment here is Phase 1, sized to ship without new infrastructure.
