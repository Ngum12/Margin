"""Versioned prompt files.

Each file starts with ``version: <name>``. The version stored with every model output is
``<name>#<first 8 hex chars of SHA-256 of the file>``, so any edit to a prompt is distinguishable
in the data even if the declared version was not bumped.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    version: str
    template: str

    def render(self, **values: str) -> str:
        # Plain substitution of {name} placeholders; other braces (JSON examples) are kept.
        text = self.template
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
        return text


@lru_cache
def load_prompt(name: str) -> Prompt:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    first, _, body = raw.partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"Prompt {name} must start with a 'version:' line")
    declared = first.removeprefix("version:").strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return Prompt(version=f"{declared}#{digest}", template=body.lstrip("\n"))
