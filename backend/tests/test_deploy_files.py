"""Deployment files (D-066): container images are pinned to exact, approved versions, and the
container's requirements match backend/uv.lock exactly."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVED = {
    "python": "3.12.15-slim",
    "node": "22.23.3-slim",
    "ollama/ollama": "0.40.5",
    "caddy": "2.11.7",
}


def _images() -> dict[str, str]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    text += (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    found = re.findall(r"(?:FROM|image:)\s+([a-z0-9./-]+):([A-Za-z0-9._-]+)", text)
    return {name: tag for name, tag in found if name != "margin"}


def test_every_image_is_pinned_to_its_approved_version() -> None:
    assert _images() == APPROVED
    assert ":latest" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_approved_images_are_recorded_in_dependencies() -> None:
    record = (ROOT / "docs" / "DEPENDENCIES.md").read_text(encoding="utf-8")
    for name, tag in APPROVED.items():
        assert f"{name}:{tag}" in record


def test_container_requirements_match_the_lockfile() -> None:
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text(encoding="utf-8"))
    locked = {p["name"].lower(): p["version"] for p in lock["package"]}
    text = (ROOT / "backend" / "requirements.lock.txt").read_text(encoding="utf-8")
    pinned = re.findall(r"^([A-Za-z0-9_.-]+)==([0-9][^\s;]*)", text, flags=re.MULTILINE)
    assert pinned
    for name, version in pinned:
        assert locked.get(name.lower().replace("_", "-")) == version, name
    assert "--hash=sha256:" in text
