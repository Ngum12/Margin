"""Subjects are configuration, not code (D-017). Each TOML file in ``configs/`` defines one
subject for one curriculum. Adding a subject means adding a file."""

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

CONFIG_DIR = Path(__file__).parent / "configs"

Code = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,49}$")]


class LocalizedName(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    en: str
    fr: str


class ReaderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # Subject-specific transcription notation, given to the Reader model (Phase 3).
    notation_hints: tuple[str, ...] = ()


class SubjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: Code
    curriculum: Code
    names: LocalizedName
    reader: ReaderConfig = ReaderConfig()


class SubjectRegistry:
    def __init__(self, subjects: list[SubjectConfig]) -> None:
        self._by_key: dict[tuple[str, str], SubjectConfig] = {}
        for subject in subjects:
            key = (subject.curriculum, subject.code)
            if key in self._by_key:
                raise ValueError(f"Duplicate subject {subject.code} for {subject.curriculum}")
            self._by_key[key] = subject

    @classmethod
    def from_directory(cls, directory: Path) -> "SubjectRegistry":
        subjects = []
        for path in sorted(directory.glob("*.toml")):
            with path.open("rb") as f:
                subjects.append(SubjectConfig.model_validate(tomllib.load(f)))
        return cls(subjects)

    def for_curriculum(self, curriculum: str) -> list[SubjectConfig]:
        return sorted(
            (s for (c, _), s in self._by_key.items() if c == curriculum),
            key=lambda s: s.names.en,
        )

    def get(self, curriculum: str, code: str) -> SubjectConfig | None:
        return self._by_key.get((curriculum, code))


@lru_cache
def get_registry() -> SubjectRegistry:
    return SubjectRegistry.from_directory(CONFIG_DIR)
