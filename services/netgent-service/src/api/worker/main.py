"""Worker entrypoint and shared Procrastinate app factory."""

from __future__ import annotations

import logging

from api.worker import get_queue_app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    queue_app = get_queue_app()
    queue_app.run_worker()


if __name__ == "__main__":
    main()
