-- SQL*Plus/SQLcl reconciliation: sent = terminal successes + dead letters.
WITH counts AS (
  SELECT
    COUNT(DISTINCT CASE WHEN stage='queued' AND status='success' THEN order_id END) sent,
    COUNT(DISTINCT CASE WHEN stage='processed' AND status IN ('processed','inventory_rejected') THEN order_id END) processed,
    COUNT(DISTINCT CASE WHEN stage='failed' AND status='dead_lettered' THEN order_id END) dead_lettered
  FROM pipeline_events
)
SELECT sent, processed, dead_lettered, sent-processed-dead_lettered unreconciled,
       CASE WHEN sent=processed+dead_lettered THEN 'PASS' ELSE 'FAIL' END reconciled
FROM counts;

-- Queued messages with neither a processed row nor a durable DLQ transition.
SELECT q.order_id, MIN(q.event_time) queued_at
FROM pipeline_events q
LEFT JOIN processed_orders p ON p.order_id=q.order_id
LEFT JOIN pipeline_events d ON d.order_id=q.order_id AND d.stage='failed' AND d.status='dead_lettered'
WHERE q.stage='queued' AND q.status='success' AND p.order_id IS NULL AND d.order_id IS NULL
GROUP BY q.order_id ORDER BY queued_at;

-- Database rows lacking a queued audit event (manual writes or audit gaps).
SELECT p.order_id, p.processed_at
FROM processed_orders p
LEFT JOIN pipeline_events q ON q.order_id=p.order_id AND q.stage='queued' AND q.status='success'
WHERE q.event_id IS NULL;
