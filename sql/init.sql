WHENEVER SQLERROR EXIT SQL.SQLCODE
CONNECT mq_user/mq_password@localhost:1521/FREEPDB1

CREATE TABLE inventory (
    sku VARCHAR2(80) PRIMARY KEY,
    available NUMBER(10) NOT NULL CHECK (available >= 0)
);

MERGE INTO inventory i USING (
  SELECT 'WIDGET-A' sku, 10000 available FROM dual UNION ALL
  SELECT 'WIDGET-B', 10000 FROM dual UNION ALL
  SELECT 'GADGET-C', 10000 FROM dual UNION ALL
  SELECT 'OUT-OF-STOCK', 0 FROM dual
) seed ON (i.sku=seed.sku)
WHEN MATCHED THEN UPDATE SET i.available=seed.available
WHEN NOT MATCHED THEN INSERT (sku,available) VALUES(seed.sku,seed.available);

CREATE TABLE processed_orders (
    order_id VARCHAR2(80) PRIMARY KEY,
    customer_id VARCHAR2(80) NOT NULL,
    source_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    subtotal NUMBER(12,2) NOT NULL,
    tax NUMBER(12,2) NOT NULL,
    grand_total NUMBER(12,2) NOT NULL,
    status VARCHAR2(30) NOT NULL CHECK (status IN ('PROCESSED', 'INVENTORY_REJECTED')),
    shortage_skus VARCHAR2(2000),
    payload CLOB CHECK (payload IS JSON),
    correlation_id VARCHAR2(36) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE pipeline_events (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_time TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    order_id VARCHAR2(80),
    stage VARCHAR2(40) NOT NULL,
    status VARCHAR2(40) NOT NULL,
    detail VARCHAR2(4000)
);
CREATE INDEX ix_pipeline_events_order ON pipeline_events(order_id, event_time);
COMMIT;
