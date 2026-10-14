-- Additive V7 table: adaptive-scaffold (help) events for the structured mentor.
-- Append-only. Records each help request and the scaffold the participant was shown,
-- WITHOUT duplicating the learner/tutor attempt text held in v5_stage_attempts /
-- v5_exchanges. "Where should I look?" pointers are location cues only. The paper
-- is opened by the separate consultation control and logged in v5_consultation_events.
CREATE TABLE IF NOT EXISTS v5_scaffold_events (
  event_id TEXT PRIMARY KEY,
  participant_id TEXT NOT NULL,
  period INTEGER NOT NULL CHECK(period IN (1,2)),
  paper_id TEXT NOT NULL,
  structured_stage TEXT,
  required_exchange_number INTEGER NOT NULL CHECK(required_exchange_number BETWEEN 1 AND 5),
  exchange_id TEXT REFERENCES v5_exchanges(exchange_id),
  event_type TEXT NOT NULL,          -- help_request
  help_type TEXT NOT NULL,           -- explain_question | explain_feedback | hint | source_pointer | example | unsure
  pre_attempt INTEGER NOT NULL CHECK(pre_attempt IN (0,1)),
  scaffold_level INTEGER NOT NULL DEFAULT 0,
  attempt_number INTEGER NOT NULL DEFAULT 0,   -- substantive attempts made in this stage at time of request
  pointer_ref TEXT,                  -- for source_pointer: the exact verified location shown
  pointer_paper_id TEXT,             -- paper the pointer was drawn from (must equal paper_id)
  scaffold_text TEXT NOT NULL,       -- the text shown to the participant
  model_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(participant_id,period) REFERENCES v5_periods(participant_id,period)
);
