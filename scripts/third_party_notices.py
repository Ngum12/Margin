#!/usr/bin/env python3
"""Generate THIRD_PARTY_NOTICES.md from the licence files of everything we ship.

Covers the font files bundled for marked PDFs (from their manifest), the backend runtime
dependency closure (from backend/pyproject.toml, read with the
installed package metadata, including native libraries bundled in wheels such as PDFium and
Pillow's image libraries) and the frontend runtime packages bundled into frontend/dist.

Run inside the backend environment (it needs the installed packages):

    cd backend && uv run python ../scripts/third_party_notices.py          # write the file
    cd backend && uv run python ../scripts/third_party_notices.py --check  # verify it is current

``--check`` verifies that every shipped package and version is listed. Licence texts of bundled
native libraries can differ slightly between platform builds, so they are not compared byte for
byte; regenerate the file whenever dependencies change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.md"
_LICENCE_NAME = re.compile(r"(licen[cs]e|notice|copying|authors)", re.IGNORECASE)


@dataclass(frozen=True)
class Component:
    ecosystem: str
    name: str
    version: str
    licence: str
    texts: list[tuple[str, str]]  # (file label, text)

    @property
    def key(self) -> str:
        return f"{self.ecosystem}:{self.name.lower()}=={self.version}"


def _python_closure() -> list[str]:
    pyproject = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    env = {k: str(v) for k, v in default_environment().items()}
    pending = [Requirement(r).name for r in pyproject["project"]["dependencies"]]
    seen: dict[str, str] = {}
    while pending:
        name = pending.pop()
        canonical = name.lower().replace("_", "-")
        if canonical in seen:
            continue
        dist = metadata.distribution(name)
        seen[canonical] = dist.metadata["Name"]
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is not None and not req.marker.evaluate({**env, "extra": ""}):
                continue
            pending.append(req.name)
    return sorted(seen.values(), key=str.lower)


def _python_component(name: str) -> Component:
    dist = metadata.distribution(name)
    meta = dist.metadata
    licence = meta.get("License-Expression") or ""
    if not licence:
        licence = (meta.get("License") or "").splitlines()[0][:80] if meta.get("License") else ""
    if not licence:
        classifiers = [
            c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if "License" in c
        ]
        licence = ", ".join(classifiers) or "see licence text"
    texts = []
    for file in sorted(dist.files or [], key=str):
        path = str(file).replace("\\", "/")
        if ".dist-info/" in path and _LICENCE_NAME.search(path.rsplit("/", 1)[-1]):
            label = path.split(".dist-info/", 1)[1]
            label = re.sub(r"data/[^/]+/BUILD_LICENSES/", "bundled/", label)
            texts.append(
                (
                    label,
                    Path(str(dist.locate_file(file))).read_text(encoding="utf-8", errors="replace"),
                )
            )
    return Component("python", meta["Name"], dist.version, licence, texts)


def _frontend_components() -> list[Component]:
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    components = []
    for path, info in sorted(lock["packages"].items()):
        # Runtime packages only; TypeScript appears as an optional peer but is never bundled.
        if (
            not path
            or info.get("dev")
            or info.get("peer")
            or path.endswith("node_modules/typescript")
        ):
            continue
        folder = ROOT / "frontend" / path
        name = path.split("node_modules/")[-1]
        texts = (
            [
                (f.name, f.read_text(encoding="utf-8", errors="replace"))
                for f in sorted(folder.iterdir())
                if f.is_file() and _LICENCE_NAME.search(f.name)
            ]
            if folder.is_dir()
            else []
        )
        components.append(
            Component("npm", name, info["version"], info.get("license", "see licence text"), texts)
        )
    return components


def _font_components() -> list[Component]:
    """Font files bundled with the app (marked PDFs), listed in their manifest."""
    folder = ROOT / "backend" / "app" / "exports" / "fonts"
    families = json.loads((folder / "fonts.json").read_text(encoding="utf-8"))
    return [
        Component(
            "font",
            family["name"],
            family["version"],
            family["licence"],
            [
                (
                    family["licence_file"],
                    (folder / family["licence_file"]).read_text(encoding="utf-8"),
                )
            ],
        )
        for family in families
    ]


def collect() -> list[Component]:
    return (
        [_python_component(n) for n in _python_closure()]
        + _frontend_components()
        + _font_components()
    )


def render(components: list[Component]) -> str:
    lines = [
        "# Third-party notices",
        "",
        "The Marking Assistant includes the following third-party software. Each component is",
        "listed with its version and licence, followed by the licence and notice texts it ships.",
        "Generated by `scripts/third_party_notices.py`; do not edit by hand.",
        "",
        "## Summary",
        "",
        "| Component | Version | Licence | Ecosystem |",
        "|---|---|---|---|",
    ]
    lines += [f"| {c.name} | {c.version} | {c.licence} | {c.ecosystem} |" for c in components]
    for c in components:
        lines += [
            "",
            "---",
            "",
            f"## {c.name} {c.version} ({c.ecosystem})",
            "",
            f"Licence: {c.licence}",
        ]
        if not c.texts:
            lines += [
                "",
                "_No licence file is shipped with this package; licence as declared above._",
            ]
        for label, text in c.texts:
            lines += ["", f"### {label}", "", "```text", text.rstrip().replace("```", "'''"), "```"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    components = collect()
    if args.check:
        if not OUTPUT.is_file():
            print("THIRD_PARTY_NOTICES.md is missing; run scripts/third_party_notices.py")
            return 1
        existing = OUTPUT.read_text(encoding="utf-8")
        missing = [
            c.key for c in components if f"## {c.name} {c.version} ({c.ecosystem})" not in existing
        ]
        if missing:
            print("THIRD_PARTY_NOTICES.md is out of date. Missing:", ", ".join(missing))
            print("Regenerate: cd backend && uv run python ../scripts/third_party_notices.py")
            return 1
        print(f"THIRD_PARTY_NOTICES.md lists all {len(components)} shipped components.")
        return 0
    OUTPUT.write_text(render(components), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.name}: {len(components)} components.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
