"""Background worker entry point: ``python -m app.worker`` (run from backend/)."""

import logging
import signal
import sys

from app.config import get_settings
from app.db.session import make_engine, make_sessionmaker
from app.logging_config import configure_logging
from app.startup_checks import UnsafeConfigurationError, check_startup_safety
from app.worker.runner import Worker


def main() -> int:
    settings = get_settings()
    configure_logging(settings)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s worker %(levelname)s %(message)s"))
    logging.getLogger().addHandler(console)
    try:
        check_startup_safety(settings)
    except UnsafeConfigurationError as exc:
        print(exc, file=sys.stderr)
        return 2
    worker = Worker(make_sessionmaker(make_engine(settings)), settings)
    signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        worker.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
