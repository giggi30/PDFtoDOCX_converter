import logging
import time

from app.workers.tasks import cleanup_expired_jobs

logger = logging.getLogger(__name__)


def run(interval_seconds: int = 60) -> None:
    while True:
        try:
            cleanup_expired_jobs()
        except Exception:
            logger.exception("Temporary artifact cleanup failed")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run()
