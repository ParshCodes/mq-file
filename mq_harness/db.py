import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Any
import oracledb


def connect(settings):
    return oracledb.connect(
        user=settings.oracle_user, password=settings.oracle_password, dsn=settings.oracle_dsn
    )


def record_event(conn, order_id: str | None, stage: str, status: str, detail: str | None = None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_events(order_id, stage, status, detail) VALUES (:1, :2, :3, :4)",
            (order_id, stage, status, detail),
        )


def process_order(settings, order: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Inventory check and order write share a transaction; duplicate deliveries are idempotent."""
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT order_id, status, tax, grand_total FROM processed_orders WHERE order_id=:1",
                (order["order_id"],),
            )
            existing = cur.fetchone()
            if existing:
                record_event(conn, order["order_id"], "processed", "duplicate_ignored")
                conn.commit()
                return {"order_id": existing[0], "status": existing[1], "duplicate": True}

            shortages = []
            for item in order["items"]:
                cur.execute("SELECT available FROM inventory WHERE sku=:1 FOR UPDATE", (item["sku"],))
                row = cur.fetchone()
                if row is None or row[0] < item["quantity"]:
                    shortages.append(item["sku"])

            subtotal = Decimal(str(order["total"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            # Monetary tax uses round-half-up: 50.00 * 8.25% = 4.125 -> 4.13.
            tax = (subtotal * Decimal("0.0825")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            status = "INVENTORY_REJECTED" if shortages else "PROCESSED"
            if not shortages:
                for item in order["items"]:
                    cur.execute(
                        "UPDATE inventory SET available=available-:1 WHERE sku=:2",
                        (item["quantity"], item["sku"]),
                    )
            cur.execute(
                """INSERT INTO processed_orders
                   (order_id, customer_id, source_timestamp, subtotal, tax, grand_total,
                    status, shortage_skus, payload, correlation_id)
                   VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10)""",
                (
                    order["order_id"], order["customer"]["id"],
                    datetime.fromisoformat(order["timestamp"].replace("Z", "+00:00")), subtotal,
                    tax, subtotal + tax, status, ",".join(shortages), json.dumps(order), correlation_id,
                ),
            )
            record_event(conn, order["order_id"], "processed", status.lower())
        conn.commit()
    return {"order_id": order["order_id"], "status": status, "tax": tax, "grand_total": subtotal + tax}
