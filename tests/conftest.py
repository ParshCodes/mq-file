import json
import os
import shutil
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def stack_available():
    try:
        import pika
        conn = pika.BlockingConnection(pika.ConnectionParameters(
            "localhost", credentials=pika.PlainCredentials(
                os.getenv("RABBITMQ_USER", "mq_user"), os.getenv("RABBITMQ_PASSWORD", "mq_password")
            ), socket_timeout=1,
        ))
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def integration_stack():
    if not stack_available():
        pytest.skip("Docker integration stack is not running")
    return ROOT


@pytest.fixture
def db(integration_stack):
    import oracledb
    conn = oracledb.connect(
        user=os.getenv("ORACLE_USER", "mq_user"),
        password=os.getenv("ORACLE_USER_PASSWORD", "mq_password"),
        dsn=os.getenv("ORACLE_TEST_DSN", "localhost:1521/FREEPDB1"),
    )
    yield conn
    conn.close()


def unique_order(order: dict, prefix="ORD-TEST"):
    result = json.loads(json.dumps(order))
    result["order_id"] = f"{prefix}-{uuid.uuid4().hex[:12]}"
    return result


def submit_json(root: Path, order: dict, name: str | None = None):
    path = root / "incoming" / (name or f"{order['order_id']}.json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(order), encoding="utf-8")
    temporary.rename(path)  # producer never observes a partially written test file
    return path


def wait_until(predicate, timeout=45, interval=.25):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s; last result={last!r}")


@pytest.fixture
def valid_order():
    return json.loads((ROOT / "sample_data" / "valid_order.json").read_text(encoding="utf-8"))
