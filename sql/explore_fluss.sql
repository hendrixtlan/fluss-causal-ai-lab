-- Execute one statement at a time in Flink SQL client after `bridge-fluss`.
-- The physical Fluss tables are created by the Python native SDK.
CREATE CATALOG fluss_catalog WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'coordinator-server:9123'
);
USE CATALOG fluss_catalog;
USE causal_lab;
SHOW TABLES;
SET 'execution.runtime-mode' = 'batch';
SELECT account_id, kind, valid_at, observed_at, event_id FROM event_log;
SELECT account_id, risk_score, knowledge_at, outcome FROM account_state;
SELECT decision_id, outcome, evidence_sha256 FROM decision_log;
-- No assumption that these SQL queries expose native bucket positions.
