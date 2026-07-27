import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_lock = Lock()


class EventLogger:
    """Writes one complete JSON object per line, safely across local threads."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.console = logging.getLogger("mq_harness")
        if not self.console.handlers:
            logging.basicConfig(level=logging.INFO, format="%(message)s")

    def emit(self, order_id: str | None, stage: str, status: str, **fields: Any) -> dict:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "order_id": order_id,
            "stage": stage,
            "status": status,
            **{k: v for k, v in fields.items() if v is not None},
        }
        line = json.dumps(event, separators=(",", ":"), default=str)
        with _lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        self.console.info(line)
        return event

