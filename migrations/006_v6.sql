-- Additive V6 table: full learner reasoning trail for the adaptive structured mentor.
-- Every attempt (including revisions after feedback) is preserved append-only, so
-- INITIAL RESPONSE -> FEEDBACK -> REVISION -> FINAL RESPONSE is reconstructable.
-- No assessment items, options, or answer keys are stored here.
CREATE TABLE IF NOT EXISTS v5_stage_attempts (
  attempt_id TEXT PRIMARY KEY,
  exchange_id TEXT NOT NULL REFERENCES v5_exchanges(exchange_id),
  participant_id TEXT NOT NULL,
  period INTEGER NOT NULL CHECK(period IN (1,2)),
  required_exchange_number INTEGER NOT NULL CHECK(required_exchange_number BETWEEN 1 AND 5),
  structured_stage TEXT,
  condition TEXT NOT NULL,
  attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 20),
  learner_response TEXT NOT NULL,
  classification TEXT,
  present_concepts_json TEXT,
  missing_concepts_json TEXT,
  misconception TEXT,
  sufficient INTEGER CHECK(sufficient IN (0,1)),
  hint_level INTEGER NOT NULL DEFAULT 0,
  tutor_response TEXT,
  completion_reason TEXT,
  model_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  request_status TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  responded_at TEXT,
  UNIQUE(exchange_id, attempt_number),
  FOREIGN KEY(participant_id,period) REFERENCES v5_periods(participant_id,period)
);
