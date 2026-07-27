import json
import random
import time

from .config import Settings
from .db import connect, process_order, record_event
from .logging_utils import EventLogger
from .mq import connection, declare_topology


class Consumer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.log = EventLogger(settings.log_file)
        self.conn = connection(settings)
        self.channel = self.conn.channel()
        declare_topology(self.channel, settings)
        self.channel.basic_qos(prefetch_count=10)

    def audit_failure(self, order_id: str, detail: str):
        with connect(self.settings) as conn:
            record_event(conn, order_id, "failed", "dead_lettered", detail)
            conn.commit()

    def handle(self, channel, method, properties, body):
        started = time.perf_counter()
        order_id = properties.message_id
        correlation_id = properties.correlation_id
        self.log.emit(order_id, "processing", "started", correlation_id=correlation_id)
        try:
            order = json.loads(body)
            order_id = order.get("order_id", order_id)
            forced = order.get("force_failure") is True
            if forced or random.random() < self.settings.failure_rate:
                reason = "forced test failure" if forced else "simulated random processing failure"
                raise RuntimeError(reason)
            result = process_order(self.settings, order, correlation_id)
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            self.log.emit(
                order_id, "processed", "success", correlation_id=correlation_id,
                processing_ms=elapsed, business_status=result["status"],
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            detail = str(exc)
            try:
                self.audit_failure(order_id, detail)
            except Exception as audit_exc:
                # Do not discard the message when the durable failure audit cannot be written.
                self.log.emit(order_id, "failed", "audit_failure", error=str(audit_exc), correlation_id=correlation_id)
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                return
            self.log.emit(
                order_id, "failed", "dead_lettered", error=detail,
                correlation_id=correlation_id, processing_ms=elapsed,
            )
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

    def run(self):
        self.channel.basic_consume(queue=self.settings.queue, on_message_callback=self.handle, auto_ack=False)
        self.log.emit(None, "consumer", "started")
        self.channel.start_consuming()


def main():
    Consumer(Settings()).run()


if __name__ == "__main__":
    main()
