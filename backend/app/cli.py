"""Setup commands for a school installation. Run from backend/:

    uv run python -m app.cli migrate
    uv run python -m app.cli init-school --name "GBHS Example" --country Cameroon
    uv run python -m app.cli create-user --username admin --display-name "Head Teacher" --role admin
    uv run python -m app.cli evaluate --data eval/ --backend ollama --report report.json

Passwords are prompted for (never passed on the command line). For automation, the password can
be read from an environment variable named with --password-env.
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Language, Role, School
from app.db.session import make_engine, make_sessionmaker
from app.errors import ConflictError
from app.schemas.accounts import UserCreateIn
from app.services.users import create_user_unchecked

BACKEND_DIR = Path(__file__).resolve().parents[1]


def migrate() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    print("Database is up to date.")


def init_school(name: str, country: str, curriculum: str) -> int:
    factory = make_sessionmaker(make_engine(get_settings()))
    with factory() as db:
        if db.scalar(select(School.id)) is not None:
            print("A school already exists in this installation.", file=sys.stderr)
            return 1
        db.add(School(name=name, country=country, curriculum=curriculum))
        db.commit()
    print(f"School '{name}' created.")
    return 0


def _read_password(env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name)
        if not value:
            raise SystemExit(f"Environment variable {env_name} is not set.")
        return value
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def create_user(
    username: str, display_name: str, role: str, language: str, password_env: str | None
) -> int:
    try:
        data = UserCreateIn(
            username=username,
            display_name=display_name,
            password=_read_password(password_env),
            role=Role(role),
            preferred_language=Language(language),
        )
    except ValidationError as exc:
        fields = ", ".join(str(e["loc"][0]) for e in exc.errors())
        print(f"Invalid value for: {fields}", file=sys.stderr)
        return 1

    factory = make_sessionmaker(make_engine(get_settings()))
    with factory() as db:
        school_id = db.scalar(select(School.id))
        if school_id is None:
            print("Create the school first: init-school", file=sys.stderr)
            return 1
        try:
            create_user_unchecked(db, None, school_id, data)
        except ConflictError as exc:
            print(exc.message, file=sys.stderr)
            return 1
        db.commit()
    print(f"User '{data.username}' created ({data.role.value}).")
    return 0


def evaluate(
    data: Path, subject: str | None, backend: str | None, curriculum: str, report: Path | None
) -> int:
    """Measure the configured Reader against typed ground truth (see app.ai.evaluation)."""
    from app.ai.evaluation import evaluate as run_evaluation
    from app.ai.evaluation import find_pages
    from app.ai.factory import build_reader
    from app.subjects.registry import SubjectConfig, get_registry

    settings = get_settings()
    if backend:
        settings = settings.model_copy(update={"ai_backend": backend})
    pages = find_pages(data, subject)
    if not pages:
        print(f"No image + .txt pairs found under {data}", file=sys.stderr)
        return 1
    registry = get_registry()

    def subject_config(code: str) -> SubjectConfig:
        config = registry.get(curriculum, code)
        if config is None:
            raise SystemExit(f"Unknown subject '{code}' for curriculum {curriculum}")
        return config

    for code in pages:
        subject_config(code)  # fail fast on unknown folders
    reader = build_reader(settings)
    print(f"Reader: {reader.model.name} ({reader.model.version}), prompt {reader.prompt_version}")
    results = run_evaluation(reader, pages, subject_config, progress=print)

    print()
    print(
        f"{'subject':<14}{'pages':>6}{'CER':>8}{'WER':>8}"
        f"{'key recall':>12}{'invalid':>9}{'s/page':>9}"
    )
    for r in results:
        t = r.total
        print(
            f"{r.subject:<14}{len(r.pages):>6}{t.cer:>8.1%}{t.wer:>8.1%}"
            f"{t.key_token_recall:>12.1%}{r.invalid_outputs:>9}{r.seconds_per_page:>9.1f}"
        )
    if report:
        report.write_text(
            json.dumps(
                {
                    "reader": {
                        "model": reader.model.name,
                        "version": reader.model.version,
                        "prompt_version": reader.prompt_version,
                        "max_image_px": settings.reader_max_image_px,
                    },
                    "subjects": [
                        {
                            "subject": r.subject,
                            "pages": len(r.pages),
                            "cer": r.total.cer,
                            "wer": r.total.wer,
                            "key_token_recall": r.total.key_token_recall,
                            "invalid_outputs": r.invalid_outputs,
                            "seconds_per_page": r.seconds_per_page,
                            "page_results": [
                                {
                                    "name": p.name,
                                    "seconds": p.seconds,
                                    "valid_output": p.valid_output,
                                    "cer": p.score.cer,
                                    "wer": p.score.wer,
                                    "key_token_recall": p.score.key_token_recall,
                                }
                                for p in r.pages
                            ],
                        }
                        for r in results
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Report written to {report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="create or upgrade the database schema")

    school = sub.add_parser("init-school", help="create the school record (once)")
    school.add_argument("--name", required=True)
    school.add_argument("--country", required=True)
    school.add_argument("--curriculum", default="cm_gce_ol")

    user = sub.add_parser("create-user", help="create an administrator or teacher")
    user.add_argument("--username", required=True)
    user.add_argument("--display-name", required=True)
    user.add_argument("--role", choices=[r.value for r in Role], default=Role.TEACHER.value)
    user.add_argument("--language", choices=[lang.value for lang in Language], default="en")
    user.add_argument("--password-env", help="read the password from this environment variable")

    ev = sub.add_parser("evaluate", help="measure the Reader against typed ground truth")
    ev.add_argument(
        "--data", type=Path, required=True, help="folder of <subject>/<page>.jpg + .txt"
    )
    ev.add_argument("--subject", help="only this subject folder")
    ev.add_argument("--backend", choices=["mock", "ollama"], help="override MARGIN_AI_BACKEND")
    ev.add_argument("--curriculum", default="cm_gce_ol")
    ev.add_argument("--report", type=Path, help="write a JSON report here")

    args = parser.parse_args(argv)
    if args.command == "evaluate":
        return evaluate(args.data, args.subject, args.backend, args.curriculum, args.report)
    if args.command == "migrate":
        migrate()
        return 0
    if args.command == "init-school":
        return init_school(args.name, args.country, args.curriculum)
    return create_user(
        args.username, args.display_name, args.role, args.language, args.password_env
    )


if __name__ == "__main__":
    sys.exit(main())
