"""Slide-reading quality test: runs the real slide analysis on slides whose
contents are known, scores how much it read correctly, and reports what it
cost. With --b it runs a second setting on the same slides and compares the
two, so a cheaper setting can be shown not to read slides worse before it
ships.

This calls the real model and costs real money (a fraction of a cent a
slide on claude-haiku-5-5), so it is run by hand, not in pytest/CI:

    cd backend && ANTHROPIC_API_KEY=sk-ant-... python ../tools/quality/run_eval.py
    cd backend && python ../tools/quality/run_eval.py --b effort=low
    cd backend && python ../tools/quality/run_eval.py --a max_edge=1600 --b max_edge=1024 --runs 3

A setting is comma-separated key=value pairs:
    effort=low|medium|high   the analyzer's effort (production: medium)
    max_edge=N               shrink the image so its longer side is at most N pixels first
    model=...                the model (production: anthropic_vlm_model in app/core/config.py)

Exit status is 1 when --b's average score is more than --tolerance below --a's.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "backend"))
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import anthropic
from PIL import Image
from scoring import CaseScore, score_case

from app.core.config import get_settings
from app.services.claude_vlm_analyzer import ClaudeVLMAnalyzer
from app.services.usage import accumulated_cost_usd, start_accumulator

_KEYS = {"effort", "max_edge", "model"}


@dataclass
class Setting:
    label: str
    effort: str = "medium"
    max_edge: int | None = None
    model: str = field(default_factory=lambda: get_settings().anthropic_vlm_model)

    @classmethod
    def parse(cls, label: str, text: str) -> Setting:
        setting = cls(label=label)
        for pair in filter(None, (part.strip() for part in text.split(","))):
            key, _, value = pair.partition("=")
            if key not in _KEYS or not value:
                raise SystemExit(f"--{label.lower()}: unknown setting {pair!r} (use {', '.join(sorted(_KEYS))})")
            setattr(setting, key, int(value) if key == "max_edge" else value)
        return setting

    def describe(self) -> str:
        return f"{self.model}, effort={self.effort}" + (f", max_edge={self.max_edge}" if self.max_edge else "")


@dataclass
class Run:
    score: CaseScore
    cost_usd: float
    input_tokens: int
    output_tokens: int
    seconds: float


def shrink(image_bytes: bytes, max_edge: int | None) -> bytes:
    """The image with its longer side at most `max_edge` pixels, as PNG; unchanged if already that small."""
    if not max_edge:
        return image_bytes
    image = Image.open(io.BytesIO(image_bytes))
    if max(image.size) <= max_edge:
        return image_bytes
    image.thumbnail((max_edge, max_edge), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


async def run_case(analyzer: ClaudeVLMAnalyzer, setting: Setting, case: dict, cases_dir: Path) -> Run:
    image_bytes = shrink((cases_dir / case["image"]).read_bytes(), setting.max_edge)
    usage = start_accumulator()
    started = time.monotonic()
    try:
        result = await analyzer.analyze(image_bytes)
        score = score_case(case, result.summary, result.objects)
    except Exception as error:  # noqa: BLE001 - a failed or unparseable analysis is a quality result too
        score = CaseScore(image=case["image"], error=f"{type(error).__name__}: {error}")
    return Run(
        score=score,
        cost_usd=accumulated_cost_usd(setting.model, usage),
        input_tokens=usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens,
        output_tokens=usage.output_tokens,
        seconds=time.monotonic() - started,
    )


async def run_setting(
    client: anthropic.AsyncAnthropic,
    setting: Setting,
    cases: list[dict],
    cases_dir: Path,
    runs: int,
) -> list[list[Run]]:
    """runs × cases, one at a time (as a student captures them, and kind to rate limits)."""
    analyzer = ClaudeVLMAnalyzer(client=client, model=setting.model, effort=setting.effort)
    results: list[list[Run]] = []
    for case in cases:
        per_case = []
        for _ in range(runs):
            per_case.append(await run_case(analyzer, setting, case, cases_dir))
            mark = "x" if per_case[-1].score.error else "."
            print(mark, end="", flush=True)
        results.append(per_case)
    print()
    return results


async def evaluate(api_key: str, settings: list[Setting], cases: list[dict], cases_dir: Path, runs: int) -> list[dict]:
    async with anthropic.AsyncAnthropic(api_key=api_key) as client:
        summaries = []
        for setting in settings:
            print(f"{setting.label}: {setting.describe()} ", end="", flush=True)
            summaries.append(summarize(setting, await run_setting(client, setting, cases, cases_dir, runs)))
        return summaries


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(setting: Setting, results: list[list[Run]]) -> dict:
    flat = [run for per_case in results for run in per_case]
    return {
        "setting": setting.describe(),
        "score": _mean([run.score.score for run in flat]),
        "cost_per_slide_usd": _mean([run.cost_usd for run in flat]),
        "input_tokens_per_slide": _mean([run.input_tokens for run in flat]),
        "output_tokens_per_slide": _mean([run.output_tokens for run in flat]),
        "seconds_per_slide": _mean([run.seconds for run in flat]),
        "failed": sum(1 for run in flat if run.score.error),
        "cases": [
            {
                "image": per_case[0].score.image,
                "score": _mean([run.score.score for run in per_case]),
                "cost_usd": _mean([run.cost_usd for run in per_case]),
                # Everything missed in any run, with how many runs missed it.
                "missing": _missed(per_case),
                "errors": [run.score.error for run in per_case if run.score.error],
            }
            for per_case in results
        ],
    }


def _missed(per_case: list[Run]) -> list[str]:
    counts: dict[str, int] = {}
    for run in per_case:
        for item in run.score.missing:
            counts[item] = counts.get(item, 0) + 1
    runs = len(per_case)
    return [item if runs == 1 else f"{item} ({count}/{runs} runs)" for item, count in counts.items()]


def print_report(summaries: list[dict]) -> None:
    for label, summary in zip("AB", summaries):
        print(f"\n{label}: {summary['setting']}")
        for case in summary["cases"]:
            print(f"  {case['score']:6.1%}  ${case['cost_usd']:.5f}  {case['image']}")
            for item in case["missing"]:
                print(f"            missed {item}")
            for error in case["errors"]:
                print(f"            FAILED {error}")

    print("\n                 " + "".join(f"{label:>14}" for label in "AB"[: len(summaries)]))
    rows = [
        ("score", lambda s: f"{s['score']:.1%}"),
        ("cost / slide", lambda s: f"${s['cost_per_slide_usd']:.5f}"),
        ("input tokens", lambda s: f"{s['input_tokens_per_slide']:.0f}"),
        ("output tokens", lambda s: f"{s['output_tokens_per_slide']:.0f}"),
        ("seconds / slide", lambda s: f"{s['seconds_per_slide']:.1f}"),
        ("failed", lambda s: str(s["failed"])),
    ]
    for name, cell in rows:
        print(f"  {name:<15}" + "".join(f"{cell(s):>14}" for s in summaries))
    if len(summaries) == 2:
        a, b = summaries
        saving = 1 - b["cost_per_slide_usd"] / a["cost_per_slide_usd"] if a["cost_per_slide_usd"] else 0.0
        print(f"\n  B vs A: score {b['score'] - a['score']:+.1%}, cost {-saving:+.0%}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", default="", help="the baseline setting (default: production)")
    parser.add_argument("--b", default=None, help="a setting to compare against A")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="analyses per slide per setting (the model varies run to run)",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=HERE / "cases",
        help="folder with cases.json and the slide images",
    )
    parser.add_argument("--only", default=None, help="only images whose name contains this")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.02,
        help="how far B's score may fall below A's before exit status 1",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write the full results here")
    args = parser.parse_args()

    cases = json.loads((args.cases / "cases.json").read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [case for case in cases if args.only in case["image"]]
    if not cases:
        raise SystemExit("no cases")
    settings = [Setting.parse("A", args.a)] + ([Setting.parse("B", args.b)] if args.b is not None else [])

    api_key = os.environ.get("ANTHROPIC_API_KEY") or get_settings().anthropic_api_key
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY (or anthropic_api_key in backend/.env).")

    print(f"{len(cases)} slides x {args.runs} run(s) x {len(settings)} setting(s)")
    summaries = asyncio.run(evaluate(api_key, settings, cases, args.cases, args.runs))
    print_report(summaries)
    if args.json:
        args.json.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    if len(summaries) == 2 and summaries[1]["score"] < summaries[0]["score"] - args.tolerance:
        print(f"\nB reads slides worse than A by more than {args.tolerance:.0%}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
