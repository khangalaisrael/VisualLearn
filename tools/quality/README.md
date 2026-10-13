# Slide-reading quality test

Runs the real slide analysis (`ClaudeVLMAnalyzer`, the same call a capture
makes) on slides whose contents are known, and reports for each setting:

- **score**: the share of what each slide plainly shows that the analysis
  got right (object types found, text read, code lines read exactly);
- **cost per slide**, tokens and time;
- **what it missed**, slide by slide.

With `--b` it runs a second setting on the same slides and compares the two.
It exits with status 1 when B scores more than `--tolerance` (default 2
points) below A, so a cheaper setting has to prove it reads slides as well
before it ships.

It calls the real model and costs real money: well under a cent per slide on
`claude-haiku-5-5`, so a full comparison on the seed set costs a few cents.
That's why it runs by hand and not in CI.

## Running it

From `backend/`, with its virtualenv active:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # or anthropic_api_key in backend/.env

python ../tools/quality/run_eval.py                       # production setting only
python ../tools/quality/run_eval.py --b effort=low        # is "low" effort good enough?
python ../tools/quality/run_eval.py --b max_edge=1024     # are smaller images good enough?
python ../tools/quality/run_eval.py --b effort=low --runs 3 --json results.json
```

A setting is comma-separated `key=value` pairs: `effort` (`low`, `medium`,
`high`; production is `medium`), `max_edge` (shrink the image so its longer
side is at most this many pixels) and `model`. `--a` defaults to production.

The model varies from run to run, so use `--runs 3` or more before trusting a
difference of a few points. Missed items then show how many runs missed them.

## The slides

`cases/` holds the slide images and `cases/cases.json`, which says what each
one plainly shows. The seed set is seven slides from three subjects
(algorithms, Haskell, linear algebra) covering a title, bullet text, a code
block, an equation, a table and a diagram:

```json
{
  "image": "merge-sort-python.png",
  "types": ["title", "code", "paragraph"],
  "text": ["Merge Sort in Python", ["Θ(n) extra memory", "\\Theta(n) extra memory"]],
  "code": {"language": "python", "lines": ["def merge_sort(a):", "mid = len(a) // 2"]}
}
```

- `types`: object types the analysis must find. `diagram|graph` accepts either.
- `text`: strings that must appear somewhere in what it read (any object's
  text, LaTeX or summary, or the slide summary). A list inside the list
  accepts any one of its strings.
- `code`: lines a code object in that language must contain.

Text is compared ignoring spacing, case and how maths is typeset: `\frac{n}{2}`
matches `n/2`, `\Theta` matches `Θ`, `x_1` matches `x₁`, `−` matches `-`. Code
lines ignore only spacing, since an underscore or a capital letter in code is
a real misreading. The rules are in `scoring.py` and tested in
`tests/backend/test_quality_scoring.py`.

### Adding your own slides

The seed slides are clean. Real lectures aren't, so the most useful cases are
real captures, especially the kind that go wrong: small fonts, dense
equations, handwriting, photos of a projector, dark themes.

1. Save the screenshot (PNG or JPEG) into `cases/`.
2. Add an entry to `cases.json` listing what a student would need from that
   slide: the title, the key sentences, every line of code, the equations.
   Write only what's plainly on the slide. Use a list of alternatives where
   the same thing can be written two ways.
3. Run with `--only <part of the file name>` to check the new case on its
   own.

Only add slides you're allowed to share. Lecture slides usually belong to the
lecturer or the university.
