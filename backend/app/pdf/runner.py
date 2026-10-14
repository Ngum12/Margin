"""Runs app.pdf.render_worker in a child process with a timeout (D-028)."""

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.pdf import render_worker

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RenderedPage:
    index: int
    image: str
    thumb: str
    width: int
    height: int
    rotation_applied: int
    qr_texts: list[str]
    qr_damaged: int
    cover_frame: bool


@dataclass(frozen=True)
class RenderResult:
    page_count: int
    pages: list[RenderedPage]


class RenderError(Exception):
    """Rendering failed. ``code`` is an API error code shown to the teacher (translated)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def worker_command(pdf_path: Path, output_dir: Path, settings: Settings) -> list[str]:
    return [
        sys.executable,
        "-m",
        "app.pdf.render_worker",
        "--input",
        str(pdf_path),
        "--output-dir",
        str(output_dir),
        "--dpi",
        str(settings.page_dpi),
        "--quality",
        str(settings.page_jpeg_quality),
        "--max-pages",
        str(settings.max_pdf_pages),
    ]


def render_pdf(pdf_path: Path, output_dir: Path, settings: Settings) -> RenderResult:
    """Render into a fresh ``output_dir``. Raises RenderError; never lets the child crash us."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    command = worker_command(pdf_path, output_dir, settings)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed command, no shell
            command,
            cwd=BACKEND_DIR,
            capture_output=True,
            timeout=settings.render_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run has already killed the child.
        raise RenderError("upload.render_timeout", f"after {exc.timeout}s") from exc

    code = completed.returncode
    if code == render_worker.EXIT_UNREADABLE:
        raise RenderError("upload.pdf_unreadable")
    if code == render_worker.EXIT_TOO_MANY_PAGES:
        raise RenderError("upload.too_many_pages")
    manifest_path = output_dir / render_worker.MANIFEST_NAME
    if code != 0 or not manifest_path.is_file():
        # Crashed (e.g. a native fault) or exited unexpectedly. Log the exit code only.
        logger.error("Render worker exited with code %s", code)
        raise RenderError("upload.render_crashed", f"exit code {code}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return RenderResult(
        page_count=int(data["page_count"]),
        pages=[RenderedPage(**page) for page in data["pages"]],
    )
