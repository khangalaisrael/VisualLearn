# VisualLearn — Algorithms Intelligence

## Project Goal

VisualLearn is a Chrome extension that captures lecture slides and uses AI to help students understand them.

The next major capability is **Theory of Algorithms Intelligence**.

VisualLearn should be able to take an algorithms lecture slide — including equations, pseudocode, recurrence relations, complexity expressions, graphs, tables, diagrams, and definitions — and reason about it like a strong university algorithms tutor.

The goal is NOT simply to generate a longer explanation.

The goal is to make VisualLearn capable of:

- accurately reading mathematical notation
- understanding algorithms and pseudocode
- analysing time and space complexity
- solving and explaining recurrence relations
- tracing algorithms step-by-step
- explaining correctness
- explaining why an algorithm works
- comparing algorithms
- identifying common mistakes
- connecting mathematical notation to algorithmic intuition
- teaching concepts progressively
- answering follow-up questions about the current slide
- visually representing algorithmic concepts when useful

The experience should feel like having an excellent Algorithms lecturer/tutor sitting next to the student.

---

# Core Principle

## Understand first. Explain second.

Never treat the slide as ordinary text.

An algorithms slide may contain information in:

- equations
- mathematical notation
- pseudocode
- code
- graphs
- trees
- tables
- diagrams
- recurrence relations
- asymptotic notation
- definitions
- theorem statements
- proof sketches
- annotations

The system must first construct an internal understanding of the slide and only then produce the explanation.

---

# Algorithms Reasoning Pipeline

The algorithms analysis pipeline should conceptually follow:

```text
Slide Image
    ↓
Visual Extraction
    ↓
Content Classification
    ↓
Mathematical / Algorithmic Parsing
    ↓
Structured Algorithm Representation
    ↓
Reasoning
    ↓
Verification
    ↓
Teaching Explanation
    ↓
Visualisation
```

Do not collapse these stages into one generic prompt.

---

# 1. Slide Understanding

When a slide is captured, identify all meaningful elements.

Classify content into categories such as:

```text
definition
theorem
algorithm
pseudocode
code
equation
recurrence
complexity
proof
graph
tree
table
example
comparison
diagram
text
warning
notation
```

The model should preserve relationships between elements.

For example:

```text
T(n) = 2T(n/2) + n
```

should not merely be extracted as text.

It should be recognised as:

```json
{
  "type": "recurrence",
  "expression": "T(n) = 2T(n/2) + n",
  "subproblem_count": 2,
  "subproblem_size": "n/2",
  "combine_cost": "n"
}
```

---

# 2. Mathematical Understanding

Mathematical expressions must be treated as mathematical objects.

The system should distinguish:

```text
O(n)
Θ(n)
Ω(n)

log n
log₂ n

n log n
n²
2ⁿ
n!

T(n) = T(n-1) + 1
T(n) = 2T(n/2) + n
T(n) = T(n/2) + 1
```

Do not blindly trust OCR.

When mathematical notation is ambiguous, the model should explicitly state the interpretation.

Example:

> I interpret this as T(n) = 2T(n/2) + n. If the slide intended a different expression, show me and I can recalculate it.

Never silently invent missing symbols.

---

# 3. Complexity Analysis Engine

VisualLearn should be able to analyse:

## Time Complexity

Examples:

```text
O(1)
O(log n)
O(n)
O(n log n)
O(n²)
O(n³)
O(2ⁿ)
O(n!)
```

But the system must explain **why**.

Bad:

> The complexity is O(n²).

Good:

> The outer loop runs n times. For each iteration, the inner loop runs approximately n times, giving n × n operations. Therefore the dominant term is n², so the running time is Θ(n²).

The reasoning matters more than the final Big-O label.

---

# 4. Loop Analysis

Analyse nested loops structurally.

Example:

```python
for i in range(n):
    for j in range(i):
        work()
```

Do not automatically say O(n²) without reasoning.

Recognise:

```text
1 + 2 + 3 + ... + (n-1)
```

Then derive:

```text
n(n-1)/2
```

and conclude:

```text
Θ(n²)
```

The explanation should teach the student where the result came from.

---

# 5. Non-Standard Loops

Handle patterns such as:

```python
i *= 2
```

```python
i /= 2
```

```python
i += 3
```

```python
while i < n:
    i *= 2
```

Recognise logarithmic behaviour.

Example:

```text
1 → 2 → 4 → 8 → ... → n
```

Therefore:

```text
2^k = n
k = log₂ n
```

Conclusion:

```text
Θ(log n)
```

Explain the mathematical connection.

---

# 6. Sequential Operations

Recognise:

```text
O(n) + O(n²) + O(log n)
```

as:

```text
O(n²)
```

Explain that the dominant asymptotic term determines the final complexity.

Do not incorrectly multiply sequential blocks.

---

# 7. Conditional Complexity

Handle:

```python
if condition:
    O(n)
else:
    O(n²)
```

Distinguish:

- best case
- worst case
- average case

Do not automatically equate Big-O with worst case without explaining the context.

Where appropriate, distinguish:

```text
O(...)
Θ(...)
Ω(...)
```

and explain their meanings.

---

# 8. Recurrence Relations

Recurrences are a first-class feature.

Support methods including:

- substitution
- recursion-tree analysis
- Master Theorem
- iteration/unrolling
- recursion-tree intuition

For example:

```text
T(n) = 2T(n/2) + n
```

The system should be able to identify:

```text
a = 2
b = 2
f(n) = n
```

Then compare:

```text
n^(log_b a)
= n^(log₂2)
= n
```

and explain why this falls into the appropriate Master Theorem case.

The system should not merely output:

```text
Θ(n log n)
```

It should show the reasoning.

---

# 9. Recursion Trees

When a recurrence is recursive, VisualLearn should be capable of generating a conceptual recursion tree.

For:

```text
T(n) = 2T(n/2) + n
```

represent:

```text
                 T(n)
              /        \
          T(n/2)      T(n/2)
          /   \        /   \
       T(n/4) ...    ...   ...
```

Also reason about:

```text
cost per level
number of levels
total cost per level
leaf cost
```

The final explanation should connect the tree to the complexity result.

---

# 10. Master Theorem

Support the standard form:

```text
T(n) = aT(n/b) + f(n)
```

The tutor should identify:

```text
a
b
f(n)
n^(log_b a)
```

Then compare growth rates.

The explanation should teach the intuition behind the theorem rather than making it feel like a formula lookup.

When the Master Theorem does not apply, explicitly say so.

Do NOT force every recurrence into Master Theorem.

---

# 11. Recursion Analysis

For recursive algorithms, identify:

```text
base case
recursive case
number of recursive calls
input-size reduction
work outside recursion
```

Example:

```python
def binary_search(A, low, high):
    if low > high:
        return -1

    mid = (low + high) // 2

    if A[mid] == target:
        return mid
    elif A[mid] > target:
        return binary_search(A, low, mid - 1)
    else:
        return binary_search(A, mid + 1, high)
```

Explain:

```text
one recursive call
input approximately halves
constant work per call
```

therefore:

```text
T(n) = T(n/2) + O(1)
      = Θ(log n)
```

---

# 12. Algorithm Tracing

VisualLearn should be able to execute algorithms conceptually.

Given:

```text
A = [5, 2, 4, 6, 1, 3]
```

and an algorithm, provide:

```text
iteration
current variables
array state
comparisons
swaps
return value
```

For sorting algorithms, show the evolution of the array.

Examples:

- insertion sort
- selection sort
- bubble sort
- merge sort
- quicksort
- heap sort

Do not skip important state transitions.

---

# 13. Graph Algorithms

VisualLearn should deeply understand graph concepts.

Support:

```text
vertices
edges
directed graphs
undirected graphs
weighted graphs
degrees
paths
cycles
connected components
DAGs
trees
spanning trees
```

Algorithms:

```text
BFS
DFS
Dijkstra
Bellman-Ford
Floyd-Warshall
Kruskal
Prim
topological sorting
```

When a slide contains a graph, understand its structure instead of describing it vaguely.

For example:

> Vertex A is connected to B and C.

is better than:

> There is a graph with several connected nodes.

---

# 14. Graph Algorithm Complexity

Explain complexity based on representation.

For example:

```text
BFS:
Adjacency list → O(V + E)
Adjacency matrix → O(V²)
```

Do not provide a complexity without considering the underlying representation when it materially affects the answer.

Similarly distinguish implementations of:

```text
Dijkstra
priority queue
binary heap
array/matrix implementation
```

---

# 15. Sorting Algorithms

Understand and compare:

```text
Bubble Sort
Insertion Sort
Selection Sort
Merge Sort
Quick Sort
Heap Sort
Counting Sort
Radix Sort
Bucket Sort
```

For each algorithm where relevant:

```text
best case
average case
worst case
space complexity
stable?
in-place?
comparison-based?
```

Do not memorise tables only.

Explain the reason behind the complexity.

---

# 16. Searching

Support:

```text
linear search
binary search
hash-based lookup
tree search
```

For binary search, explain the logarithmic complexity mathematically.

---

# 17. Divide and Conquer

Recognise the structure:

```text
divide
solve
combine
```

Examples:

```text
Merge Sort
Quick Sort
Binary Search
```

Connect the algorithm structure to its recurrence.

---

# 18. Dynamic Programming

Recognise:

```text
overlapping subproblems
optimal substructure
state
transition
base cases
memoization
tabulation
```

When a DP algorithm is shown, explain:

1. What does the state mean?
2. What does the recurrence/transition mean?
3. What are the base cases?
4. Why does the recurrence produce the answer?
5. How many states exist?
6. How much work is done per state?
7. What is the resulting time and space complexity?

---

# 19. Greedy Algorithms

Explain:

```text
greedy choice
local optimum
global optimum
exchange argument
optimal substructure
```

Do not claim a greedy algorithm is correct merely because it works on an example.

Distinguish:

```text
algorithm appears to work
```

from:

```text
algorithm has been proven correct
```

---

# 20. Correctness

VisualLearn should teach algorithm correctness.

Recognise proof techniques such as:

```text
loop invariants
induction
contradiction
exchange arguments
structural induction
```

For loop invariants, explain:

```text
Initialization
Maintenance
Termination
```

Example:

> Before each iteration, the first i elements are sorted.

Then explain why that invariant remains true.

---

# 21. Asymptotic Notation

Teach the conceptual differences:

```text
O(g(n))
Θ(g(n))
Ω(g(n))
```

Avoid saying:

> O(n) means the algorithm takes n seconds.

Instead explain that asymptotic notation describes growth as input size increases.

When useful, provide the formal definitions:

```text
f(n) ∈ O(g(n))
```

if there exist constants:

```text
c > 0
n₀ > 0
```

such that:

```text
0 ≤ f(n) ≤ c g(n)
```

for all:

```text
n ≥ n₀
```

But adapt the explanation to the student's level.

---

# 22. Mathematical Proof Assistance

When a slide contains a proof, VisualLearn should identify:

```text
claim
assumptions
definitions
logical steps
conclusion
```

For complexity proofs, explain inequalities step-by-step.

Example:

```text
3n² + 5n + 7 = Θ(n²)
```

Show both upper and lower bound reasoning when appropriate.

---

# 23. Common Student Errors

The tutor should actively detect likely misconceptions.

Examples:

### Mistake

```text
Two nested loops always mean O(n²).
```

Correction:

> Not necessarily. It depends on how many times the inner loop actually executes.

### Mistake

```text
O(n) + O(n) = O(n²)
```

Correction:

```text
O(n) + O(n) = O(n)
```

### Mistake

```text
O(n) × O(n) because two operations occur.
```

Explain when multiplication is and is not appropriate.

### Mistake

```text
log(n) = n
```

Correct it mathematically.

### Mistake

```text
Binary search works on any array.
```

Explain the sorted-data requirement.

---

# 24. Explanation Modes

The user should be able to request different levels.

## Simple

Explain as if the student has never seen the concept.

Use intuition and small examples.

## University

Explain at undergraduate Computer Science level.

Include mathematical reasoning.

## Rigorous

Provide:

```text
formal definitions
derivations
proofs
assumptions
edge cases
complexity analysis
```

## Exam Mode

Focus on:

```text
what must be remembered
how to solve similar questions
common traps
exam-style reasoning
```

## Socratic Mode

Do not immediately reveal the answer.

Ask guiding questions.

Example:

> How many times does the outer loop execute?

Then:

> Good. Now, for a fixed i, how many times does the inner loop execute?

---

# 25. Slide Explanation Structure

When explaining an algorithms slide, prefer:

```text
1. What this slide is about
2. The key idea
3. Decode the notation
4. Walk through the algorithm
5. Explain the mathematics
6. Complexity analysis
7. Why it works
8. Example
9. Common mistake
10. One-sentence takeaway
```

Do not force every section when unnecessary.

---

# 26. Querying the Current Slide

The user can ask:

```text
Why is this O(n log n)?
```

```text
Where did this recurrence come from?
```

```text
Explain this equation.
```

```text
Why can't we use Master Theorem here?
```

```text
What does this graph mean?
```

```text
Trace this algorithm.
```

```text
Why is this algorithm correct?
```

```text
What would happen if n = 16?
```

The answer must use the current slide as primary context.

---

# 27. Context Hierarchy

When answering a query, use:

```text
1. Current slide
2. Related slides in the lecture
3. Conversation history about the concept
4. General algorithm knowledge
```

Do not answer using generic knowledge when the slide provides specific notation or assumptions.

---

# 28. Mathematical Verification

Before returning an answer involving mathematics, perform an internal consistency check.

Verify:

- algebra
- recurrence parameters
- logarithm bases where relevant
- asymptotic simplification
- loop counts
- recursive branching
- complexity classification
- inequalities
- proof logic

Never confidently present an incorrect derivation.

If uncertain, say so.

---

# 29. Complexity Verification

Before returning:

```text
O(...)
Θ(...)
Ω(...)
```

ask internally:

```text
What is the dominant operation?

How many times does it execute?

Are operations sequential or nested?

Does the input shrink?

Does recursion branch?

What is the data structure?

What assumptions are being made?
```

This should prevent superficial complexity answers.

---

# 30. Visual Learning

Algorithms are highly visual.

When useful, VisualLearn should generate or render:

```text
recursion trees
call trees
array transformations
sorting steps
graph traversals
BFS layers
DFS exploration
heap states
binary search intervals
DP tables
algorithm flow diagrams
```

Do not add visuals merely for decoration.

Every visual must help explain the reasoning.

---

# 31. Interactive Mathematics

Where the UI supports interactive graphs or mathematical visualisation, use them for concepts where visualisation materially improves understanding.

Examples:

```text
growth rates
recursion trees
function growth
binary search intervals
algorithm state transitions
```

Do not replace a rigorous explanation with a visual.

The visual is supporting evidence.

---

# 32. Structured Internal Representation

Where practical, represent algorithm understanding using structured data.

Example:

```json
{
  "concept": "merge sort",
  "type": "divide_and_conquer",
  "input": "array",
  "divide": "split array into two halves",
  "recursive_step": "sort each half",
  "combine": "merge sorted halves",
  "recurrence": "T(n) = 2T(n/2) + Θ(n)",
  "complexity": {
    "time": "Θ(n log n)",
    "space": "Θ(n)"
  }
}
```

This representation should support downstream explanation and visualisation.

---

# 33. Architecture

Keep the algorithms reasoning layer separate from:

```text
Chrome extension UI
image capture
authentication
database
general AI chat
```

Prefer a dedicated algorithms analysis pipeline.

Conceptually:

```text
SlideCapture
    ↓
VisionAnalysis
    ↓
SlideStructure
    ↓
AlgorithmParser
    ↓
MathAnalyzer
    ↓
ComplexityAnalyzer
    ↓
ProofAnalyzer
    ↓
TeachingEngine
    ↓
VisualisationEngine
```

Do not create one giant prompt that attempts to perform everything.

---

# 34. AI Prompt Design

Prompts should enforce:

```text
accuracy > verbosity
reasoning > answer memorisation
slide context > generic explanation
verification > confident guessing
teaching > summarisation
```

The model should be instructed to expose useful reasoning to the student, while keeping internal chain-of-thought private.

Provide concise derivations, intermediate mathematical steps, and explanations that are appropriate for the learner.

Do NOT expose hidden model reasoning or internal chain-of-thought.

---

# 35. Grounding

When explaining a slide, clearly distinguish:

```text
WHAT THE SLIDE SAYS
```

from:

```text
ADDITIONAL EXPLANATION
```

If the model adds information not present on the slide, it should not imply that the lecturer stated it.

Example:

> The slide gives the recurrence T(n) = 2T(n/2) + n. To understand why this leads to Θ(n log n), we can analyse the recursion tree...

---

# 36. Error Handling

If the slide is unclear:

```text
I can read most of the equation, but the symbol after T(n/2) is unclear.
```

If the algorithm is incomplete:

```text
The pseudocode appears to be missing the termination condition, so I can't reliably determine the complexity.
```

Never hallucinate missing mathematical symbols or code.

---

# 37. Performance

Do not run expensive analysis unnecessarily.

Use progressive analysis:

```text
Fast:
slide classification
OCR / vision extraction
basic explanation

On demand:
complexity analysis
proof analysis
recurrence solving
algorithm tracing

Deep analysis:
multi-slide concept linking
formal proof
comparative analysis
```

Cache structured slide understanding so repeated questions do not require reprocessing the image.

---

# 38. User Experience

The student should be able to select a slide and immediately see:

```text
Explain
Simplify
Analyse complexity
Break down equation
Trace algorithm
Why does this work?
Test me
Ask anything
```

For algorithm-heavy slides, surface relevant actions automatically.

For example:

```text
Recurrence detected

→ Solve recurrence
→ Explain recursion tree
→ Find complexity
```

or:

```text
Pseudocode detected

→ Trace algorithm
→ Find time complexity
→ Explain correctness
```

---

# 39. Quality Standard

VisualLearn should eventually be capable of handling a university-level Algorithms and Complexity course covering topics such as:

```text
asymptotic analysis
recurrences
divide and conquer
sorting
searching
hashing
heaps
priority queues
trees
BSTs
balanced trees
graphs
BFS
DFS
shortest paths
minimum spanning trees
dynamic programming
greedy algorithms
NP-completeness
correctness proofs
```

The target is not:

> "AI that summarises algorithms slides."

The target is:

> **An interactive algorithms tutor that can see, analyse, derive, visualise, and teach what is happening on the slide.**

---

# 40. Development Rule

Before implementing a feature, ask:

> Does this help VisualLearn understand algorithms, or does it merely make the AI response longer?

Prefer:

```text
better parsing
better mathematical reasoning
better verification
better visualisation
better interaction
```

over:

```text
longer explanations
more UI
more buttons
more generic AI text
```

The ultimate product should make a student look at a difficult algorithms slide and think:

> "I can actually see what is happening here."

That is the standard.
