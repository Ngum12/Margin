"""``python -m app.cli evaluate``: compare Readers (and Markers) on a labelled set.

    uv run python -m app.cli evaluate --data <folder> --backend ollama --models vision \\
        --mark-schemes <folder with mark scheme CSVs> --expected-marks expected_marks.csv \\
        --report report.json

``--models vision`` evaluates every installed Ollama model that reports the vision capability;
a comma-separated list names models explicitly. Each model is used both as Reader and Marker.
Marking is evaluated twice when expected marks are given: on the model's own transcription
(the real pipeline) and on the true transcription (the marker alone, without reading errors).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.eval_cache import EvalCache
from app.ai.evaluation import SubjectReport, evaluate, find_scripts
from app.ai.factory import build_marker, build_reader, ollama_client
from app.ai.marking_evaluation import (
    MarkingSummary,
    evaluate_marking,
    exam_spec_from_csv,
    find_mark_scheme,
    load_expected,
)
from app.ai.orientation_evaluation import (
    OrientationPage,
    OrientationSummary,
    evaluate_orientation,
)
from app.ai.types import ExamSpec
from app.ai.validation import ORIENTATIONS
from app.config import Settings, get_settings
from app.subjects.registry import SubjectConfig, get_registry


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data", type=Path, required=True, help="<subject>/<student>/page*.jpg + truth.txt"
    )
    parser.add_argument("--subject", help="only this subject folder")
    parser.add_argument("--backend", choices=["mock", "ollama"], help="override MARGIN_AI_BACKEND")
    parser.add_argument(
        "--models",
        help='comma-separated Ollama models, "vision" (all installed vision models) or "none"',
    )
    parser.add_argument("--curriculum", default="cm_gce_ol")
    parser.add_argument(
        "--mark-schemes", type=Path, help="folder with one mark scheme CSV per subject"
    )
    parser.add_argument(
        "--expected-marks", type=Path, help="CSV: subject,student,question,expected_marks,category"
    )
    parser.add_argument(
        "--marking-input",
        choices=["both", "reader", "truth"],
        default="both",
        help="mark the model's transcription, the true transcription, or both",
    )
    parser.add_argument(
        "--marking-only-models",
        help="comma-separated models (e.g. text models) that only mark the true transcriptions",
    )
    parser.add_argument(
        "--evidence",
        default=None,
        help='marker evidence designs to compare, e.g. "quote,lines" (default: the setting)',
    )
    parser.add_argument(
        "--orientation",
        action="store_true",
        help="also measure the Reader's orientation judgement (pages fed turned in memory)",
    )
    parser.add_argument(
        "--orientation-turns",
        default="0,90,180,270",
        help="clockwise turns to feed each labelled page (default: 0,90,180,270)",
    )
    parser.add_argument(
        "--orientation-extra",
        action="append",
        default=[],
        metavar="SUBJECT:ORIENTATION:IMAGE",
        help="an extra page with a known orientation, e.g. chemistry:upside_down:page.jpg",
    )
    parser.add_argument("--report", type=Path, help="write a JSON report here")
    parser.add_argument(
        "--cache",
        type=Path,
        help="resume file (default: next to --report); finished calls are skipped on rerun",
    )


@dataclass
class ModelRun:
    model: str
    reader_version: str
    prompt_version: str
    reading: list[SubjectReport]  # empty for the second evidence design and marking-only models
    marking: dict[str, MarkingSummary]  # "reader" / "truth" -> summary
    evidence: str = "quote"
    marker_prompt_version: str = ""
    orientation: OrientationSummary | None = None

    @property
    def label(self) -> str:
        return f"{self.model} [{self.evidence}]" if self.marking else self.model


def _models(settings: Settings, requested: str | None) -> list[str]:
    if settings.ai_backend == "mock":
        return ["mock"]
    if not requested:
        return [settings.reader_model]
    if requested == "none":  # marking-only runs
        return []
    if requested == "vision":
        found = ollama_client(settings).models_with_capability("vision")
        if not found:
            raise SystemExit("No installed Ollama model reports the vision capability.")
        return found
    return [m.strip() for m in requested.split(",") if m.strip()]


def _reading_rows(run: ModelRun) -> tuple[int, float, float, float, int, float]:
    pages = sum(r.pages for r in run.reading)
    total_chars = sum(r.total.char_total for r in run.reading)
    cer = sum(r.total.char_edits for r in run.reading) / total_chars if total_chars else 0.0
    words = sum(r.total.word_total for r in run.reading)
    wer = sum(r.total.word_edits for r in run.reading) / words if words else 0.0
    keys = sum(r.total.key_total for r in run.reading)
    recall = sum(r.total.key_found for r in run.reading) / keys if keys else 1.0
    invalid = sum(r.invalid_pages for r in run.reading)
    seconds = [s for r in run.reading for sr in r.scripts for s in sr.page_seconds]
    return pages, cer, wer, recall, invalid, (sum(seconds) / len(seconds) if seconds else 0.0)


def _call_settings(settings: Settings) -> str:
    """Settings that change model output; part of every cache key."""
    return (
        f"px={settings.reader_max_image_px}|think={settings.model_think}"
        f"|cap={settings.model_max_output_tokens}|ctx={settings.model_context_tokens}"
    )


def _print_tables(runs: list[ModelRun]) -> None:
    print("\nReading (all subjects)")
    print(
        f"{'model':<28}{'pages':>6}{'CER':>8}{'WER':>8}"
        f"{'key recall':>12}{'invalid':>9}{'s/page':>9}"
    )
    for run in (r for r in runs if r.reading):
        pages, cer, wer, recall, invalid, spp = _reading_rows(run)
        print(
            f"{run.model:<28}{pages:>6}{cer:>8.1%}{wer:>8.1%}{recall:>12.1%}"
            f"{invalid / pages if pages else 0:>9.0%}{spp:>9.1f}"
        )
    print("\nReading by subject")
    print(f"{'model':<28}{'subject':<14}{'CER':>8}{'key recall':>12}{'s/page':>9}")
    for run in runs:
        for r in run.reading:
            print(
                f"{run.model:<28}{r.subject:<14}{r.total.cer:>8.1%}{r.total.key_token_recall:>12.1%}"
                f"{r.seconds_per_page:>9.1f}"
            )
    if any(run.marking for run in runs):
        print("\nMarking vs expected marks (per question)")
        print(
            f"{'model [evidence]':<36}{'input':<8}{'qns':>5}{'exact':>8}{'MAD':>7}{'failed':>8}"
            f"{'lang exact':>12}{'lang MAD':>10}{'lang lost':>11}{'s/script':>10}"
        )
        for run in runs:
            for source, m in run.marking.items():
                print(
                    f"{run.label:<36}{source:<8}{m.questions():>5}{m.exact_agreement():>8.0%}"
                    f"{m.mean_absolute_difference():>7.2f}{m.failed():>8}"
                    f"{m.exact_agreement(True):>12.0%}{m.mean_absolute_difference(True):>10.2f}"
                    f"{m.marks_lost(True):>11}{m.seconds_per_script:>10.1f}"
                )
    if any(run.marking for run in runs):
        print("\nMarking by subject (failed questions count as disagreements)")
        print(
            f"{'model [evidence]':<36}{'input':<8}{'subject':<14}{'exact':>7}{'within 1':>10}"
            f"{'MAD':>6}{'over':>6}{'under':>7}{'failed':>8}"
        )
        for run in runs:
            for source, m in run.marking.items():
                for subject, row in m.by_subject().items():
                    print(
                        f"{run.label:<36}{source:<8}{subject:<14}{row['exact_agreement']:>7.0%}"
                        f"{row['within_one_mark']:>10.0%}{row['mean_absolute_difference']:>6.2f}"
                        f"{row['over_marked_questions']:>6}{row['under_marked_questions']:>7}"
                        f"{row['failed']:>8}"
                    )
    oriented = [run for run in runs if run.orientation is not None]
    if oriented:
        print("\nOrientation judgement (fixed / left alone / WRONG turn / missed)")
        print(
            f"{'model':<28}{'calls':>6}{'fixed':>7}{'left':>6}{'wrong':>7}{'missed':>8}"
            f"{'judged right':>14}{'s/call':>8}"
        )
        for run in oriented:
            o = run.orientation
            if o is None:  # pragma: no cover - filtered above
                continue
            print(
                f"{run.model:<28}{len(o.cases):>6}{o.count('fixed'):>7}{o.count('left'):>6}"
                f"{o.count('wrong'):>7}{o.count('missed'):>8}"
                f"{o.judged_right / len(o.cases) if o.cases else 0:>14.0%}"
                f"{o.seconds_per_call:>8.1f}"
            )


def _report(runs: list[ModelRun], settings: Settings) -> dict[str, Any]:
    def marking_json(m: MarkingSummary) -> dict[str, Any]:
        return {
            "questions": m.questions(),
            "failed": m.failed(),
            "exact_agreement": m.exact_agreement(),
            "mean_absolute_difference": m.mean_absolute_difference(),
            "language_expression": {
                "questions": m.questions(True),
                "failed": m.failed(True),
                "exact_agreement": m.exact_agreement(True),
                "mean_absolute_difference": m.mean_absolute_difference(True),
                "marks_lost": m.marks_lost(True),
                "labelled_conceptual_error": m.language_called_conceptual(),
            },
            "seconds_per_script": m.seconds_per_script,
            "by_subject": m.by_subject(),
            "comparisons": [
                vars(c) | {"proposed_categories": list(c.proposed_categories)}
                for c in m.comparisons
            ],
        }

    return {
        "max_image_px": settings.reader_max_image_px,
        "models": [
            {
                "model": run.model,
                "version": run.reader_version,
                "prompt_version": run.prompt_version,
                "evidence": run.evidence,
                "marker_prompt_version": run.marker_prompt_version,
                "reading": [
                    {
                        "subject": r.subject,
                        "pages": r.pages,
                        "cer": r.total.cer,
                        "wer": r.total.wer,
                        "key_token_recall": r.total.key_token_recall,
                        "invalid_pages": r.invalid_pages,
                        "seconds_per_page": r.seconds_per_page,
                        "scripts": [
                            {
                                "name": s.script.name,
                                "cer": s.score.cer,
                                "key_token_recall": s.score.key_token_recall,
                                "invalid_pages": s.invalid_pages,
                                "page_seconds": s.page_seconds,
                                "transcription": s.transcription,
                            }
                            for s in r.scripts
                        ],
                    }
                    for r in run.reading
                ],
                "marking": {source: marking_json(m) for source, m in run.marking.items()},
                "orientation": run.orientation.as_json() if run.orientation else None,
            }
            for run in runs
        ],
    }


def _orientation_pages(
    args: argparse.Namespace, scripts: dict[str, list[Any]]
) -> list[OrientationPage]:
    pages = [
        OrientationPage(image, subject)
        for subject, items in scripts.items()
        for script in items
        for image in script.images
    ]
    for extra in args.orientation_extra:
        subject, _, rest = extra.partition(":")
        appears, _, image = rest.partition(":")
        if appears not in ORIENTATIONS or not Path(image).is_file():
            raise SystemExit(
                f"--orientation-extra: expected SUBJECT:ORIENTATION:IMAGE, got {extra}"
            )
        pages.append(OrientationPage(Path(image), subject, appears))
    return pages


def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.backend:
        settings = settings.model_copy(update={"ai_backend": args.backend})
    scripts = find_scripts(args.data, args.subject)
    if not scripts:
        print(f"No scripts with images and ground truth found under {args.data}", file=sys.stderr)
        return 1
    registry = get_registry()

    def subject_config(code: str) -> SubjectConfig:
        config = registry.get(args.curriculum, code)
        if config is None:
            raise SystemExit(f"Unknown subject '{code}' for curriculum {args.curriculum}")
        return config

    for code in scripts:
        subject_config(code)

    specs: dict[str, ExamSpec] = {}
    expected = None
    if args.expected_marks:
        if not args.mark_schemes:
            raise SystemExit("--expected-marks needs --mark-schemes")
        expected = load_expected(args.expected_marks)
        specs = {
            code: exam_spec_from_csv(
                find_mark_scheme(args.mark_schemes, code), subject_config(code)
            )
            for code in scripts
        }

    cache_path = args.cache or (args.report.with_suffix(".cache.jsonl") if args.report else None)
    cache = EvalCache(cache_path) if cache_path else None
    if cache is not None:
        print(f"Resume file: {cache_path} ({len(cache)} finished calls)", flush=True)

    modes = [m.strip() for m in (args.evidence or settings.marker_evidence).split(",") if m.strip()]
    orientation_pages = _orientation_pages(args, scripts) if args.orientation else []
    turns = tuple(int(t) % 360 for t in args.orientation_turns.split(",") if t.strip())
    if not set(modes) <= {"quote", "lines"}:
        raise SystemExit("--evidence takes quote, lines or both")

    runs = []
    for model in _models(settings, args.models):
        model_settings = settings.model_copy(update={"reader_model": model, "marker_model": model})
        reader = build_reader(model_settings)
        # Reading does not depend on the marker, so both evidence designs share one reading.
        read_prefix = (
            f"{model}|{reader.model.version}|{reader.prompt_version}|{_call_settings(settings)}"
        )
        print(f"\n== {model} ({reader.model.version}), prompt {reader.prompt_version}", flush=True)
        reading = evaluate(
            reader,
            scripts,
            subject_config,
            progress=lambda m: print(m, flush=True),
            cache=cache,
            cache_prefix=read_prefix,
        )
        orientation = None
        if orientation_pages:
            print("-- orientation judgement", flush=True)
            orientation = evaluate_orientation(
                reader,
                orientation_pages,
                subject_config,
                turns=turns,
                threshold=settings.orientation_min_confidence,
                progress=lambda m: print(m, flush=True),
                cache=cache,
                cache_prefix=read_prefix,
            )
        for index, mode in enumerate(modes):
            marker = build_marker(model_settings.model_copy(update={"marker_evidence": mode}))
            mark_prefix = (
                f"{model}|{marker.model.version}|{marker.prompt_version}|{_call_settings(settings)}"
            )
            marking: dict[str, MarkingSummary] = {}
            if expected is not None:
                print(f"-- marking, evidence design: {mode}", flush=True)
                sources = (
                    ["reader", "truth"] if args.marking_input == "both" else [args.marking_input]
                )
                for source in sources:
                    items = [
                        (
                            r.subject,
                            s.script.name,
                            s.transcription
                            if source == "reader"
                            else s.script.truth.read_text("utf-8"),
                        )
                        for r in reading
                        for s in r.scripts
                    ]
                    marking[source] = evaluate_marking(
                        marker,
                        items,
                        specs,
                        expected,
                        progress=lambda m: print(m, flush=True),
                        cache=cache,
                        cache_prefix=f"{mark_prefix}|{source}",
                    )
            runs.append(
                ModelRun(
                    model,
                    reader.model.version,
                    reader.prompt_version,
                    reading if index == 0 else [],
                    marking,
                    evidence=mode,
                    marker_prompt_version=marker.prompt_version,
                    orientation=orientation if index == 0 else None,
                )
            )

    if args.marking_only_models:
        if expected is None:
            raise SystemExit("--marking-only-models needs --expected-marks and --mark-schemes")
        truth_items = [
            (code, script.name, script.truth.read_text("utf-8"))
            for code, items in scripts.items()
            for script in items
        ]
        for model in [m.strip() for m in args.marking_only_models.split(",") if m.strip()]:
            for mode in modes:
                marker = build_marker(
                    settings.model_copy(update={"marker_model": model, "marker_evidence": mode})
                )
                prefix = (
                    f"{model}|{marker.model.version}|{marker.prompt_version}"
                    f"|{_call_settings(settings)}"
                )
                print(f"\n== {model} ({marker.model.version}), marking only, {mode}", flush=True)
                summary = evaluate_marking(
                    marker,
                    truth_items,
                    specs,
                    expected,
                    progress=lambda m: print(m, flush=True),
                    cache=cache,
                    cache_prefix=f"{prefix}|truth",
                )
                runs.append(
                    ModelRun(
                        model,
                        marker.model.version,
                        "-",
                        [],
                        {"truth": summary},
                        evidence=mode,
                        marker_prompt_version=marker.prompt_version,
                    )
                )

    _print_tables(runs)
    if args.report:
        args.report.write_text(json.dumps(_report(runs, settings), indent=2), encoding="utf-8")
        print(f"\nReport written to {args.report}")
    return 0
