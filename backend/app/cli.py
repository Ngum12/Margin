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
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select

from app import backup, demo
from app.ai import eval_cli
from app.config import get_settings
from app.db.models import Exam, Language, Role, School
from app.db.session import make_engine, make_sessionmaker
from app.errors import ConflictError
from app.schemas.accounts import UserCreateIn
from app.services import ai_marking
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


def rerun_ai(exam_id: int) -> int:
    """Re-run AI marking for an exam's unconfirmed scripts (an administrator's tool, for
    example after switching from the test models to a real one). Audited as the system."""
    settings = get_settings()
    if settings.ai_backend == "mock":
        print(
            "MARGIN_AI_BACKEND is mock: the re-run would use the test models. "
            "Set MARGIN_AI_BACKEND=ollama first.",
            file=sys.stderr,
        )
        return 1
    factory = make_sessionmaker(make_engine(settings))
    with factory() as db:
        exam = db.get(Exam, exam_id)
        if exam is None:
            print(f"No exam with id {exam_id}", file=sys.stderr)
            return 1
        try:
            count = ai_marking.rerun_exam(db, None, exam, settings)
        except ConflictError as exc:
            print(exc.message, file=sys.stderr)
            return 1
        db.commit()
    print(f"Re-running AI marking for {count} script(s) of exam {exam_id}. The worker does it.")
    return 0


def seed_demo(password_env: str | None) -> int:
    password = _read_password(password_env)
    factory = make_sessionmaker(make_engine(get_settings()))
    with factory() as db:
        try:
            username, exam_id = demo.seed_demo(db, password)
        except (LookupError, demo.DemoExistsError, ConflictError) as exc:
            print(exc, file=sys.stderr)
            return 1
        db.commit()
    print(f"Demo ready: sign in as '{username}'. Exam {exam_id} has cover sheets to print.")
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

    ev = sub.add_parser("evaluate", help="measure Readers and Markers against labelled data")
    eval_cli.add_arguments(ev)

    rerun = sub.add_parser("rerun-ai", help="re-run AI marking for an exam's unconfirmed scripts")
    rerun.add_argument("--exam", type=int, required=True, help="exam id")

    bk = sub.add_parser("backup", help="back up the database and stored files to a zip")
    bk.add_argument("--out", type=Path, help="zip to write (default: data/backups/)")

    rs = sub.add_parser("restore", help="restore a backup zip (stop Margin first)")
    rs.add_argument("--archive", type=Path, required=True)
    rs.add_argument("--force", action="store_true", help="replace the current data")

    sd = sub.add_parser("seed-demo", help="add a demo teacher, class and ready exam (once)")
    sd.add_argument("--password-env", help="read the demo password from this environment variable")

    args = parser.parse_args(argv)
    if args.command == "seed-demo":
        return seed_demo(args.password_env)
    if args.command == "backup":
        print(f"Backup written to {backup.backup(get_settings(), args.out)}")
        return 0
    if args.command == "restore":
        try:
            backup.restore(get_settings(), args.archive, force=args.force)
        except (FileExistsError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Restored. Run `python -m app.cli migrate`, then start Margin.")
        return 0
    if args.command == "evaluate":
        return eval_cli.run(args)
    if args.command == "migrate":
        migrate()
        return 0
    if args.command == "init-school":
        return init_school(args.name, args.country, args.curriculum)
    if args.command == "rerun-ai":
        return rerun_ai(args.exam)
    return create_user(
        args.username, args.display_name, args.role, args.language, args.password_env
    )


if __name__ == "__main__":
    sys.exit(main())
