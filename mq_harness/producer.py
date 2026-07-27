import json
import shutil
import time
import uuid
from pathlib import Path

import pika

from .config import Settings
from .db import connect, record_event
from .logging_utils import EventLogger
from .mq import connection, declare_topology
from .validation import DecimalEncoder, OrderValidationError, OrderValidator


def safe_destination(directory: Path, source: Path) -> Path:
    destination = directory / source.name
    if destination.exists():
        destination = directory / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix}"
    return destination


class Producer:
    def __init__(self, settings: Settings):
        self.settings = settings
        for directory in (settings.incoming, settings.rejected, settings.archive):
            directory.mkdir(parents=True, exist_ok=True)
        self.validator = OrderValidator(settings.schemas)
        self.log = EventLogger(settings.log_file)
        self.conn = connection(settings)
        self.channel = self.conn.channel()
        declare_topology(self.channel, settings)
        self.channel.confirm_delivery()

    def audit(self, order_id, stage, status, detail=None):
        try:
            with connect(self.settings) as conn:
                record_event(conn, order_id, stage, status, detail)
                conn.commit()
        except Exception as exc:
            self.log.emit(order_id, "audit", "failed", error=str(exc))

    def process_file(self, path: Path) -> bool:
        order_id = None
        correlation_id = str(uuid.uuid4())
        self.log.emit(None, "received", "success", file_name=path.name, correlation_id=correlation_id)
        try:
            order = self.validator.parse(path)
            order_id = order["order_id"]
            self.log.emit(order_id, "validated", "success", file_name=path.name, correlation_id=correlation_id)
            body = json.dumps(order, cls=DecimalEncoder, separators=(",", ":")).encode()
            # With publisher confirms enabled, pika signals an unconfirmed publish by
            # raising NackError (and unroutable mandatory messages by UnroutableError).
            # A successful BlockingChannel.basic_publish returns None, not True.
            self.channel.basic_publish(
                exchange="",
                routing_key=self.settings.queue,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                    content_type="application/json",
                    message_id=order_id,
                    correlation_id=correlation_id,
                    timestamp=int(time.time()),
                ),
                mandatory=True,
            )
            self.audit(order_id, "queued", "success")
            self.log.emit(order_id, "queued", "success", correlation_id=correlation_id)
            shutil.move(str(path), safe_destination(self.settings.archive, path))
            return True
        except (OrderValidationError, json.JSONDecodeError) as exc:
            detail = str(exc)
            self.audit(order_id, "validated", "failure", detail)
            self.log.emit(order_id, "validated", "failure", error=detail, file_name=path.name, correlation_id=correlation_id)
            shutil.move(str(path), safe_destination(self.settings.rejected, path))
            return False
        except Exception as exc:
            # Broker or infrastructure errors stay in incoming for retry; data errors are rejected.
            self.log.emit(order_id, "queued", "failure", error=str(exc), file_name=path.name, correlation_id=correlation_id)
            return False

    def run(self):
        self.log.emit(None, "producer", "started")
        while True:
            for path in sorted(self.settings.incoming.iterdir()):
                if path.is_file() and path.suffix.lower() in (".xml", ".json"):
                    self.process_file(path)
            time.sleep(0.5)


def main():
    Producer(Settings()).run()


if __name__ == "__main__":
    main()
