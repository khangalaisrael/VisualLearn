"""Loads versioned prompt templates from the top-level `prompts/` directory
(docs/PROMPTS.md §1 "Versioning"; delivered in Milestone 2 with the first
real prompt, `analysis.v1`).

Path resolution relies on this file's directory nesting
(backend/app/core/prompt_loader.py, four levels below the repo root) being
identical in local dev and in the Docker image — see backend/Dockerfile,
which deliberately keeps `backend/` as a real subdirectory rather than
flattening the image layout, specifically so this computation doesn't need
an environment-specific branch.
"""

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Load a prompt template by file stem, e.g. `load_prompt("analysis.v1")`."""
    settings = get_settings()
    prompts_dir = Path(settings.prompts_dir) if settings.prompts_dir else _DEFAULT_PROMPTS_DIR
    path = prompts_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8").strip()
