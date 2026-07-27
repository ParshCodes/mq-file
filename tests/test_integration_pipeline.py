import json
import shutil
import uuid
from pathlib import Path

import pytest

pika = pytest.importorskip("pika", reason="integration dependencies are not installed")

from conftest import submit_json, unique_order, wait_until

pytestmark = pytest.mark.integration


def fetch_order(db, order_id):
    with db.cursor() as cur:
        cur.execute("SELECT status, subtotal, tax, grand_total FROM processed_orders WHERE order_id=:1", (order_id,))
        return cur.fetchone()


def event_exists(db, order_id, stage, status):
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM pipeline_events WHERE order_id=:1 AND stage=:2 AND status=:3",
            (order_id, stage, status),
        )
        return cur.fetchone()[0] > 0


def dlq_contains(channel, order_id):
    """Inspect one queue snapshot and restore every message without assuming queue order."""
    state = channel.queue_declare(queue="orders.dead", passive=True)
    deliveries = []
    found = False
    for _ in range(state.method.message_count):
        method, _properties, body = channel.basic_get("orders.dead", auto_ack=False)
        if method is None:
            break
        deliveries.append(method.delivery_tag)
        if json.loads(body).get("order_id") == order_id:
            found = True
    for delivery_tag in deliveries:
        channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
    return found


def test_known_good_reaches_oracle_with_correct_calculation(integration_stack, db, valid_order):
    order = unique_order(valid_order, "ORD-GOOD")
    submit_json(integration_stack, order)
    row = wait_until(lambda: fetch_order(db, order["order_id"]))
    assert row[0] == "PROCESSED"
    assert float(row[1]) == 50.00
    assert float(row[2]) == 4.13
    assert float(row[3]) == 54.13


def test_malformed_file_is_rejected_with_reason(integration_stack, db):
    token = uuid.uuid4().hex[:10]
    name = f"invalid-{token}.json"
    source = integration_stack / "incoming" / name
    source.write_text('{"order_id": "ORD-BROKEN",', encoding="utf-8")
    rejected = integration_stack / "rejected" / name
    wait_until(rejected.exists)
    log = (integration_stack / "logs/pipeline.jsonl").read_text(encoding="utf-8")
    assert name in log and "malformed JSON" in log


def test_burst_of_50_has_no_message_loss(integration_stack, db, valid_order):
    ids = []
    for _ in range(50):
        order = unique_order(valid_order, "ORD-BURST")
        ids.append(order["order_id"])
        submit_json(integration_stack, order)

    def processed_count():
        placeholders = ",".join(f":{i+1}" for i in range(len(ids)))
        with db.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM processed_orders WHERE order_id IN ({placeholders})", ids)
            return cur.fetchone()[0]

    assert wait_until(lambda: processed_count() == 50, timeout=90) is True
    assert len(set(ids)) == 50


def test_forced_failure_reaches_dead_letter_queue(integration_stack, db, valid_order):
    order = unique_order(valid_order, "ORD-DLQ")
    order["force_failure"] = True
    submit_json(integration_stack, order)
    wait_until(lambda: event_exists(db, order["order_id"], "failed", "dead_lettered"))
    assert fetch_order(db, order["order_id"]) is None

    credentials = pika.PlainCredentials("mq_user", "mq_password")
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost", credentials=credentials))
    channel = conn.channel()
    try:
        wait_until(lambda: dlq_contains(channel, order["order_id"]), timeout=15)
    finally:
        conn.close()
