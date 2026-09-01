from __future__ import annotations

import hashlib
import logging
from typing import Any

import orjson

LOGGER = logging.getLogger("companion.events")


def configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    LOGGER.info(orjson.dumps(payload).decode("utf-8"))


def hash_session(session_id: object) -> str:
    return hashlib.sha256(str(session_id).encode()).hexdigest()[:16]
