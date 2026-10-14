"""V4 persistence, assignment, tutor, event, lifecycle, and export helpers.

All migrations are additive. Existing V3 rows remain in the shared versioned
tables and every V4 query is scoped to ``study_version == 'v4'``.
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Iterable, Optional

from config import (
    CONSENT_VERSION, DEMO_MODE, IRB_AMENDMENT_APPROVED, LLM_PROVIDER,
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    OPENAI_TEMPERATURE, OPENAI_TOP_P, OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE, OPENROUTER_BASE_URL, OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL, RECRUITMENT_OPEN, RECRUITMENT_TARGET_COMPLETIONS,
    V4_DESIGN_MODEL, V4_TUTOR_MAX_TOKENS,
)
from data.study_v4 import (
    GENERIC_TUTOR_PROMPT, MENTOR_QUESTIONS, MENTOR_STAGES, PAPERS,
    PRETEST_ITEMS, PROMPT_VERSION, SEQUENCES, STRUCTURED_TUTOR_PROMPT,
    STUDY_VERSION, assessment_items, sequence_periods, sequence_table,
)
from db_utils import db_placeholder, db_query, get_connection, using_postgres


TOTAL_EXPERIMENT_SECONDS = 45 * 60
MIN_READING_SECONDS = 20
STAGES = [
    "pretest",
    "paper_1_read", "paper_1_tutor", "paper_1_quiz", "paper_1_measures",
    "paper_2_read", "paper_2_tutor", "paper_2_quiz", "paper_2_measures",
    "final_survey",
]
STAGE_SECONDS = {
    "pretest": 5 * 60,
    "paper_1_read": 8 * 60, "paper_1_tutor": 7 * 60,
    "paper_1_quiz": 5 * 60, "paper_1_measures": 2 * 60,
    "paper_2_read": 8 * 60, "paper_2_tutor": 7 * 60,
    "paper_2_quiz": 5 * 60, "paper_2_measures": 2 * 60,
    "final_survey": 4 * 60,
}
ACTIVE_STATUS = "active"
LIFECYCLE_STATES = {"active", "completed", "withdrawn", "timeout", "invalid", "post_target", "test"}
SUPPORTED_CONDITIONS = {"generic", "structured"}
DEFAULT_DESIGN_MODEL = "between_subjects"
# Frozen default for legacy enrollment; persisted assignments still control resume.
V4_DESIGN_MODEL = "between_subjects"
ACTIVE_SEQUENCES = sequence_table(V4_DESIGN_MODEL)
IMMUTABLE_ASSIGNMENT_FIELDS = {
    "session_id", "study_version", "experiment_version", "assigned_sequence", "condition_name",
    "paper_order_json", "condition_order_json", "design_model", "consent_version", "consented_at", "is_test",
}
FINAL_REQUIRED_COMPONENTS = {
    "trust_item_1", "trust_item_2", "trust_item_3", "tutor_helpfulness",
    "noticed_ai_discrepancy", "ai_use_strategy_text", "prohibited_tool_report",
    "material_interruption",
}
RAW_TABLES = {
    "study_sessions_v2", "responses_v2", "chat_events_v2", "study_events_v4",
    "paper_metrics_v4", "item_timing_v4",
}


class RecruitmentClosed(RuntimeError):
    pass


@contextmanager
def connection():
    database = get_connection()
    try:
        with database:
            yield database
    finally:
        database.close()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: Optional[str], default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default


def _table_columns(database, table: str) -> set[str]:
    if using_postgres():
        rows = database.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s",
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {row["name"] for row in database.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_columns(database, table: str, additions: dict[str, str]) -> None:
    existing = _table_columns(database, table)
    for name, declaration in additions.items():
        if name not in existing:
            database.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def initialize_v4_database() -> None:
    """Create the V4 schema without deleting or rewriting any V3 record."""
    with connection() as database:
        database.execute(
            """CREATE TABLE IF NOT EXISTS study_sessions_v2 (
                session_id TEXT PRIMARY KEY, experiment_version TEXT NOT NULL,
                consent_version TEXT NOT NULL, prompt_version TEXT NOT NULL,
                assigned_sequence TEXT NOT NULL, current_stage TEXT NOT NULL,
                status TEXT NOT NULL, overall_started_at TEXT NOT NULL,
                overall_deadline_at TEXT NOT NULL, stage_started_at TEXT NOT NULL,
                completed_at TEXT, demographics_json TEXT NOT NULL,
                adherence_json TEXT NOT NULL, model_config_json TEXT NOT NULL,
                tutor_fidelity_failure INTEGER NOT NULL DEFAULT 0,
                timeout_count INTEGER NOT NULL DEFAULT 0, exclusion_reason TEXT,
                consented_at TEXT, is_test INTEGER NOT NULL DEFAULT 0,
                completion_valid INTEGER NOT NULL DEFAULT 0, completion_rank INTEGER,
                last_activity_at TEXT
            )"""
        )
        _ensure_columns(database, "study_sessions_v2", {
            "study_version": "TEXT", "condition_name": "TEXT",
            "paper_order_json": "TEXT", "mentor_state_json": "TEXT",
            "final_survey_started_at": "TEXT", "final_survey_finished_at": "TEXT",
            # Added for the within-subjects design. Nullable: rows written before this existed
            # are between_subjects with a single condition_name, and are read that way.
            "design_model": "TEXT", "condition_order_json": "TEXT",
        })
        database.execute(
            """CREATE TABLE IF NOT EXISTS responses_v2 (
                response_key TEXT PRIMARY KEY, session_id TEXT NOT NULL, phase INTEGER,
                topic TEXT, condition_name TEXT, stage TEXT NOT NULL, item_id TEXT NOT NULL,
                component TEXT NOT NULL, answer_json TEXT NOT NULL, confidence REAL,
                correctness INTEGER, response_time_seconds REAL, recorded_at TEXT NOT NULL
            )"""
        )
        _ensure_columns(database, "responses_v2", {
            "study_version": "TEXT", "paper_id": "TEXT", "presentation_period": "INTEGER",
            "question_category": "TEXT", "response_started_at": "TEXT",
            "response_submitted_at": "TEXT", "response_time_ms": "INTEGER",
            "presentation_order": "INTEGER",
        })
        database.execute(
            """CREATE TABLE IF NOT EXISTS chat_events_v2 (
                event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, phase INTEGER NOT NULL,
                condition_name TEXT NOT NULL, turn_index INTEGER NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, recorded_at TEXT NOT NULL, latency_seconds REAL,
                provider TEXT, model TEXT, prompt_version TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
                error_text TEXT, prompt_tokens INTEGER, completion_tokens INTEGER
            )"""
        )
        _ensure_columns(database, "chat_events_v2", {
            "study_version": "TEXT", "paper_id": "TEXT", "mentor_stage": "TEXT",
            "latency_ms": "INTEGER", "error_status": "TEXT",
        })
        database.execute(
            """CREATE TABLE IF NOT EXISTS participant_identity_v2 (
                session_id TEXT PRIMARY KEY, participant_name TEXT NOT NULL, recorded_at TEXT NOT NULL
            )"""
        )
        database.execute(
            """CREATE TABLE IF NOT EXISTS study_events_v4 (
                event_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL,
                study_version TEXT NOT NULL, paper_id TEXT, condition_name TEXT,
                event_type TEXT NOT NULL, recorded_at TEXT NOT NULL, metadata_json TEXT NOT NULL
            )"""
        )
        database.execute(
            """CREATE TABLE IF NOT EXISTS paper_metrics_v4 (
                metric_key TEXT PRIMARY KEY, participant_id TEXT NOT NULL,
                study_version TEXT NOT NULL, paper_id TEXT NOT NULL,
                condition_name TEXT NOT NULL, presentation_period INTEGER NOT NULL,
                reading_started_at TEXT, reading_finished_at TEXT, reading_duration_seconds REAL,
                tutor_started_at TEXT, tutor_finished_at TEXT, tutor_duration_seconds REAL,
                quiz_started_at TEXT, quiz_finished_at TEXT, quiz_duration_seconds REAL,
                paper_reopen_count INTEGER NOT NULL DEFAULT 0,
                paper_reopen_started_at TEXT, paper_reopen_finished_at TEXT,
                paper_reopen_duration_seconds REAL NOT NULL DEFAULT 0,
                paper_view_seconds_during_tutor REAL NOT NULL DEFAULT 0,
                mentor_stage TEXT, mentor_completed_central_finding INTEGER NOT NULL DEFAULT 0,
                mentor_completed_methodology INTEGER NOT NULL DEFAULT 0,
                mentor_completed_evidence INTEGER NOT NULL DEFAULT 0,
                mentor_completed_critical_perspective INTEGER NOT NULL DEFAULT 0,
                mentor_completed_warranted_interpretation INTEGER NOT NULL DEFAULT 0,
                mentor_fidelity_complete INTEGER NOT NULL DEFAULT 0,
                number_of_user_turns INTEGER NOT NULL DEFAULT 0,
                number_of_ai_turns INTEGER NOT NULL DEFAULT 0,
                participant_word_count INTEGER NOT NULL DEFAULT 0,
                assistant_word_count INTEGER NOT NULL DEFAULT 0,
                mental_effort INTEGER, predicted_score INTEGER, actual_score INTEGER,
                calibration_signed INTEGER, calibration_absolute INTEGER,
                verification_self_report INTEGER, measures_completed_at TEXT
            )"""
        )
        database.execute(
            """CREATE TABLE IF NOT EXISTS item_timing_v4 (
                response_key TEXT PRIMARY KEY, participant_id TEXT NOT NULL,
                study_version TEXT NOT NULL, stage TEXT NOT NULL, item_id TEXT NOT NULL,
                presentation_order INTEGER NOT NULL, started_at TEXT NOT NULL, submitted_at TEXT
            )"""
        )
        database.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_v2_experiment_completion_rank ON study_sessions_v2 (experiment_version, completion_rank)"
        )
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_v4_events_participant ON study_events_v4 (participant_id, recorded_at)"
        )


def active_provider() -> str:
    if LLM_PROVIDER in {"openrouter", "openai"}:
        return LLM_PROVIDER
    return "openrouter" if OPENROUTER_API_KEY else "openai"


def model_config() -> dict[str, Any]:
    provider = active_provider()
    return {
        "provider": provider,
        "model": OPENROUTER_MODEL if provider == "openrouter" else OPENAI_MODEL,
        "temperature": OPENAI_TEMPERATURE,
        "top_p": OPENAI_TOP_P,
        "max_tokens": V4_TUTOR_MAX_TOKENS,
        "reasoning": tutor_reasoning_config(provider, OPENROUTER_MODEL),
        "transport_version": "v4-visible-answer-1",
    }


def tutor_reasoning_config(provider: str, model: str) -> Optional[dict[str, bool]]:
    # DeepSeek V4 defaults to high reasoning. Its thinking can consume the entire
    # completion budget before message.content starts. This model supports
    # non-thinking mode; use it consistently in both randomized conditions.
    if provider == "openrouter" and model.startswith("deepseek/deepseek-v4-"):
        return {"enabled": False, "exclude": True}
    return None


def _valid_completion_count(database) -> int:
    row = database.execute(
        "SELECT COUNT(*) AS n FROM study_sessions_v2 WHERE study_version = " + db_placeholder() + " AND completion_valid = 1",
        (STUDY_VERSION,),
    ).fetchone()
    return int(row["n"])


def recruitment_summary() -> dict[str, Any]:
    initialize_v4_database()
    with connection() as database:
        completed = _valid_completion_count(database)
        active = database.execute(
            "SELECT COUNT(*) AS n FROM study_sessions_v2 WHERE study_version = " + db_placeholder() +
            " AND status = " + db_placeholder() + " AND is_test = 0",
            (STUDY_VERSION, ACTIVE_STATUS),
        ).fetchone()
    return {
        "valid_completions": completed,
        "target": RECRUITMENT_TARGET_COMPLETIONS,
        "active": int(active["n"]),
        "open": bool(IRB_AMENDMENT_APPROVED and RECRUITMENT_OPEN and completed < RECRUITMENT_TARGET_COMPLETIONS),
    }


def allocation_counts() -> dict[str, Any]:
    """Researcher diagnostic: condition totals and every cell of the active design.

    Counts the same population the allocator balances on: consented, non-test V4 assignments
    enrolled under the currently configured design model. Designs are counted separately
    because their cells are not comparable and must never be pooled.
    """
    initialize_v4_database()
    with connection() as database:
        rows = database.execute(
            "SELECT assigned_sequence, COUNT(*) AS n FROM study_sessions_v2 WHERE study_version = " + db_placeholder() +
            " AND consented_at IS NOT NULL AND is_test = 0 AND COALESCE(design_model, " + db_placeholder() + ") = " + db_placeholder() +
            " GROUP BY assigned_sequence",
            (STUDY_VERSION, DEFAULT_DESIGN_MODEL, V4_DESIGN_MODEL),
        ).fetchall()
    cells = {key: 0 for key in ACTIVE_SEQUENCES}
    for row in rows:
        if row["assigned_sequence"] in cells:
            cells[row["assigned_sequence"]] = int(row["n"])
    conditions = {name: 0 for name in sorted(SUPPORTED_CONDITIONS)}
    detail = {}
    for sequence_id, count in cells.items():
        periods = sequence_periods(V4_DESIGN_MODEL, sequence_id)
        for period in periods:
            conditions[period["condition"]] += count
        detail[sequence_id] = {
            "paper_order": [item["paper_id"] for item in periods],
            "condition_order": [item["condition"] for item in periods],
            "assigned": count,
        }
    return {
        "design_model": V4_DESIGN_MODEL,
        "cells": detail,
        "conditions": conditions,
        "total_assigned": sum(cells.values()),
        "max_cell_imbalance": (max(cells.values()) - min(cells.values())) if cells else 0,
    }


def _least_assigned_sequence(database) -> str:
    rows = database.execute(
        "SELECT assigned_sequence, COUNT(*) AS n FROM study_sessions_v2 WHERE study_version = " + db_placeholder() +
        " AND consented_at IS NOT NULL AND is_test = 0 AND COALESCE(design_model, " + db_placeholder() + ") = " + db_placeholder() +
        " GROUP BY assigned_sequence",
        (STUDY_VERSION, DEFAULT_DESIGN_MODEL, V4_DESIGN_MODEL),
    ).fetchall()
    counts = {key: 0 for key in ACTIVE_SEQUENCES}
    for row in rows:
        if row["assigned_sequence"] in counts:
            counts[row["assigned_sequence"]] = int(row["n"])
    least = min(counts.values())
    return secrets.choice([key for key, value in counts.items() if value == least])


def enroll_participant(
    participant_name: str, demographics: dict[str, Any], *, is_test: bool = False,
    session_id: Optional[str] = None, forced_sequence: Optional[str] = None,
) -> dict[str, Any]:
    """Atomically create identity, immutable design assignment, consent, and timers."""
    initialize_v4_database()
    cleaned_name = " ".join(participant_name.strip().split())
    required = {"academic_level", "academic_field", "prior_ai_coursework", "llm_use_frequency", "prior_llm_research_familiarity"}
    if not cleaned_name:
        raise ValueError("Participant name is required.")
    if not required.issubset(demographics) or any(demographics.get(key) in (None, "") for key in required):
        raise ValueError("All required background fields are required.")
    if forced_sequence and (not is_test or forced_sequence not in ACTIVE_SEQUENCES):
        raise ValueError("A valid forced sequence is available only for test sessions.")
    if not is_test and not (IRB_AMENDMENT_APPROVED and RECRUITMENT_OPEN):
        raise RecruitmentClosed("V4 recruitment is closed.")
    participant_id = session_id or str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    now = started.isoformat()
    with connection() as database:
        if using_postgres():
            database.execute("LOCK TABLE study_sessions_v2 IN SHARE ROW EXCLUSIVE MODE")
        else:
            database.execute("BEGIN IMMEDIATE")
        if database.execute(
            "SELECT 1 AS present FROM study_sessions_v2 WHERE session_id = " + db_placeholder(),
            (participant_id,),
        ).fetchone():
            raise ValueError("This participant session is already enrolled.")
        if not is_test and _valid_completion_count(database) >= RECRUITMENT_TARGET_COMPLETIONS:
            raise RecruitmentClosed("The V4 completion target has been reached.")
        sequence_id = forced_sequence or _least_assigned_sequence(database)
        periods = sequence_periods(V4_DESIGN_MODEL, sequence_id)
        paper_order = [item["paper_id"] for item in periods]
        condition_order = [item["condition"] for item in periods]
        # Under within_subjects there is no single participant-level condition. Keep the legacy
        # column populated only when it is genuinely meaningful, so nothing reads a misleading value.
        session_condition = condition_order[0] if len(set(condition_order)) == 1 else "mixed"
        record = {
            "session_id": participant_id, "experiment_version": STUDY_VERSION,
            "study_version": STUDY_VERSION, "consent_version": CONSENT_VERSION,
            "prompt_version": PROMPT_VERSION, "assigned_sequence": sequence_id,
            "design_model": V4_DESIGN_MODEL,
            "condition_name": session_condition,
            "paper_order_json": dumps(paper_order),
            "condition_order_json": dumps(condition_order),
            "mentor_state_json": dumps({}), "current_stage": "pretest",
            "status": "test" if is_test else ACTIVE_STATUS,
            "overall_started_at": now,
            "overall_deadline_at": (started + timedelta(seconds=TOTAL_EXPERIMENT_SECONDS)).isoformat(),
            "stage_started_at": now, "completed_at": None,
            "demographics_json": dumps(demographics), "adherence_json": dumps({}),
            "model_config_json": dumps(model_config()), "tutor_fidelity_failure": 0,
            "timeout_count": 0, "exclusion_reason": "test" if is_test else None,
            "consented_at": now, "is_test": int(is_test), "completion_valid": 0,
            "completion_rank": None, "last_activity_at": now,
            "final_survey_started_at": None, "final_survey_finished_at": None,
        }
        columns = ", ".join(record)
        database.execute(
            f"INSERT INTO study_sessions_v2 ({columns}) VALUES ({', '.join(db_placeholder() for _ in record)})",
            list(record.values()),
        )
        database.execute(
            "INSERT INTO participant_identity_v2 (session_id, participant_name, recorded_at) VALUES (" +
            ", ".join(db_placeholder() for _ in range(3)) + ")",
            (participant_id, cleaned_name, now),
        )
        _insert_event(database, participant_id, None, session_condition, "enrollment", {
            "sequence_id": sequence_id, "paper_order": paper_order,
            "condition_order": condition_order, "design_model": V4_DESIGN_MODEL,
            "consent_version": CONSENT_VERSION, "is_test": is_test,
        }, now)
        _insert_event(database, participant_id, None, session_condition, "pretest_start", {}, now)
    return record


def get_session(participant_id: str) -> Optional[dict[str, Any]]:
    initialize_v4_database()
    with connection() as database:
        row = database.execute(
            "SELECT * FROM study_sessions_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder(),
            (participant_id, STUDY_VERSION),
        ).fetchone()
    return dict(row) if row else None


def update_session(participant_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    if "status" in fields and fields["status"] not in LIFECYCLE_STATES:
        raise ValueError(f"Unknown V4 lifecycle status: {fields['status']}")
    locked = IMMUTABLE_ASSIGNMENT_FIELDS.intersection(fields)
    if locked:
        raise ValueError(f"Randomized assignment fields are immutable after enrollment: {sorted(locked)}")
    values = {**fields, "last_activity_at": utc_now_iso()}
    assignments = ", ".join(f"{name} = {db_placeholder()}" for name in values)
    with connection() as database:
        database.execute(
            f"UPDATE study_sessions_v2 SET {assignments} WHERE session_id = {db_placeholder()} AND study_version = {db_placeholder()}",
            [*values.values(), participant_id, STUDY_VERSION],
        )


def session_design_model(session: dict[str, Any]) -> str:
    """A participant keeps the design they were enrolled under, whatever the app is set to now."""
    return str(session.get("design_model") or DEFAULT_DESIGN_MODEL)


def phase_assignment(session: dict[str, Any], period: int) -> dict[str, Any]:
    """The persisted assignment is authoritative; the sequence tables are only a fallback.

    Under between_subjects both periods share one condition. Under within_subjects each period
    carries its own, so callers must never read a single condition off the session row.
    """
    design_model = session_design_model(session)
    fallback = sequence_periods(design_model, session["assigned_sequence"])

    stored_order = loads(session.get("paper_order_json"), None)
    paper_order = list(stored_order) if isinstance(stored_order, list) and len(stored_order) == 2 else [item["paper_id"] for item in fallback]

    stored_conditions = loads(session.get("condition_order_json"), None)
    if isinstance(stored_conditions, list) and len(stored_conditions) == 2:
        conditions = list(stored_conditions)
    elif session.get("condition_name") and design_model == DEFAULT_DESIGN_MODEL:
        conditions = [session["condition_name"], session["condition_name"]]
    else:
        conditions = [item["condition"] for item in fallback]

    condition = conditions[period - 1]
    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError(f"Unsupported stored condition: {condition!r}")
    return {
        "paper_id": paper_order[period - 1], "condition": condition,
        "presentation_period": period, "design_model": design_model,
    }


def stage_elapsed_seconds(session: dict[str, Any]) -> float:
    start = parse_iso(session.get("stage_started_at"))
    return 0.0 if not start else round(max(0.0, (datetime.now(timezone.utc) - start).total_seconds()), 3)


def stage_seconds_left(session: dict[str, Any]) -> int:
    if session.get("status") not in {ACTIVE_STATUS, "test"} or session.get("current_stage") == "completed":
        return 0
    now = datetime.now(timezone.utc)
    overall = parse_iso(session.get("overall_deadline_at")) or now
    stage_start = parse_iso(session.get("stage_started_at")) or now
    stage_end = stage_start + timedelta(seconds=STAGE_SECONDS.get(session.get("current_stage"), 0))
    return max(0, int(min(overall, stage_end).timestamp() - now.timestamp()))


def next_stage(stage: str) -> Optional[str]:
    try:
        return STAGES[STAGES.index(stage) + 1]
    except (ValueError, IndexError):
        return None


def log_event(participant_id: str, event_type: str, *, paper_id: Optional[str] = None, condition: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> str:
    with connection() as database:
        return _insert_event(database, participant_id, paper_id, condition, event_type, metadata or {}, utc_now_iso())


def _insert_event(database, participant_id: str, paper_id: Optional[str], condition: Optional[str], event_type: str, metadata: dict[str, Any], recorded_at: str) -> str:
    event_id = str(uuid.uuid4())
    database.execute(
        "INSERT INTO study_events_v4 (event_id, participant_id, study_version, paper_id, condition_name, event_type, recorded_at, metadata_json) VALUES (" +
        ", ".join(db_placeholder() for _ in range(8)) + ")",
        (event_id, participant_id, STUDY_VERSION, paper_id, condition, event_type, recorded_at, dumps(metadata)),
    )
    return event_id


def _metric_key(participant_id: str, paper_id: str) -> str:
    return f"{participant_id}:{paper_id}"


def ensure_paper_metrics(participant_id: str, paper_id: str, condition: str, period: int) -> dict[str, Any]:
    key = _metric_key(participant_id, paper_id)
    with connection() as database:
        row = database.execute("SELECT * FROM paper_metrics_v4 WHERE metric_key = " + db_placeholder(), (key,)).fetchone()
        if not row:
            database.execute(
                "INSERT INTO paper_metrics_v4 (metric_key, participant_id, study_version, paper_id, condition_name, presentation_period, mentor_stage) VALUES (" +
                ", ".join(db_placeholder() for _ in range(7)) + ")",
                (key, participant_id, STUDY_VERSION, paper_id, condition, period, MENTOR_STAGES[0] if condition == "structured" else None),
            )
            row = database.execute("SELECT * FROM paper_metrics_v4 WHERE metric_key = " + db_placeholder(), (key,)).fetchone()
    return dict(row)


def get_paper_metrics(participant_id: str, paper_id: str) -> Optional[dict[str, Any]]:
    with connection() as database:
        row = database.execute("SELECT * FROM paper_metrics_v4 WHERE metric_key = " + db_placeholder(), (_metric_key(participant_id, paper_id),)).fetchone()
    return dict(row) if row else None


def _update_metrics(participant_id: str, paper_id: str, fields: dict[str, Any]) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{name} = {db_placeholder()}" for name in fields)
    with connection() as database:
        database.execute(
            f"UPDATE paper_metrics_v4 SET {assignments} WHERE metric_key = {db_placeholder()}",
            [*fields.values(), _metric_key(participant_id, paper_id)],
        )


def start_paper_stage(session: dict[str, Any], period: int, kind: str) -> dict[str, Any]:
    assignment = phase_assignment(session, period)
    metrics = ensure_paper_metrics(session["session_id"], assignment["paper_id"], assignment["condition"], period)
    column = f"{kind}_started_at"
    if kind not in {"reading", "tutor", "quiz"}:
        raise ValueError("Unknown timed paper stage")
    if not metrics.get(column):
        now = utc_now_iso()
        _update_metrics(session["session_id"], assignment["paper_id"], {column: now})
        log_event(session["session_id"], f"{kind}_start" if kind != "reading" else "paper_read_start", paper_id=assignment["paper_id"], condition=assignment["condition"], metadata={"presentation_period": period})
    return get_paper_metrics(session["session_id"], assignment["paper_id"]) or metrics


def finish_paper_stage(session: dict[str, Any], period: int, kind: str) -> None:
    assignment = phase_assignment(session, period)
    metrics = start_paper_stage(session, period, kind)
    now = datetime.now(timezone.utc)
    started = parse_iso(metrics.get(f"{kind}_started_at")) or now
    duration = round(max(0.0, (now - started).total_seconds()), 3)
    _update_metrics(session["session_id"], assignment["paper_id"], {
        f"{kind}_finished_at": now.isoformat(), f"{kind}_duration_seconds": duration,
    })
    event_type = {"reading": "paper_read_end", "tutor": "tutor_end", "quiz": "quiz_end"}[kind]
    log_event(session["session_id"], event_type, paper_id=assignment["paper_id"], condition=assignment["condition"], metadata={"duration_seconds": duration, "presentation_period": period})


def set_paper_view(participant_id: str, paper_id: str, condition: str, is_open: bool) -> None:
    metrics = get_paper_metrics(participant_id, paper_id)
    if not metrics:
        raise ValueError("Paper metrics must exist before a tutor paper view.")
    now = datetime.now(timezone.utc)
    if is_open and not metrics.get("paper_reopen_started_at"):
        _update_metrics(participant_id, paper_id, {
            "paper_reopen_started_at": now.isoformat(),
            "paper_reopen_count": int(metrics.get("paper_reopen_count") or 0) + 1,
        })
        log_event(participant_id, "paper_open", paper_id=paper_id, condition=condition)
    elif not is_open and metrics.get("paper_reopen_started_at"):
        started = parse_iso(metrics["paper_reopen_started_at"]) or now
        duration = round(max(0.0, (now - started).total_seconds()), 3)
        total = float(metrics.get("paper_view_seconds_during_tutor") or 0) + duration
        _update_metrics(participant_id, paper_id, {
            "paper_reopen_started_at": None, "paper_reopen_finished_at": now.isoformat(),
            "paper_reopen_duration_seconds": duration,
            "paper_view_seconds_during_tutor": round(total, 3),
        })
        log_event(participant_id, "paper_close", paper_id=paper_id, condition=condition, metadata={"duration_seconds": duration})


def ensure_item_started(participant_id: str, stage: str, item_id: str, order: int) -> str:
    key = f"{participant_id}:{stage}:{item_id}:answer"
    with connection() as database:
        row = database.execute("SELECT started_at FROM item_timing_v4 WHERE response_key = " + db_placeholder(), (key,)).fetchone()
        if row:
            return str(row["started_at"])
        now = utc_now_iso()
        database.execute(
            "INSERT INTO item_timing_v4 VALUES (" + ", ".join(db_placeholder() for _ in range(8)) + ")",
            (key, participant_id, STUDY_VERSION, stage, item_id, order, now, None),
        )
    return now


def save_response(
    participant_id: str, stage: str, item_id: str, component: str, answer: Any, *,
    paper_id: Optional[str] = None, condition: Optional[str] = None,
    presentation_period: Optional[int] = None, question_category: Optional[str] = None,
    presentation_order: Optional[int] = None, correctness: Optional[bool] = None,
) -> None:
    key = f"{participant_id}:{stage}:{item_id}:{component}"
    submitted = utc_now_iso()
    started_at = submitted
    if component == "answer":
        started_at = ensure_item_started(participant_id, stage, item_id, presentation_order or 0)
    start_dt = parse_iso(started_at) or datetime.now(timezone.utc)
    end_dt = parse_iso(submitted) or start_dt
    response_ms = max(0, round((end_dt - start_dt).total_seconds() * 1000))
    values = (
        key, participant_id, presentation_period, paper_id, condition, stage, item_id,
        component, dumps(answer), None, None if correctness is None else int(correctness),
        response_ms / 1000, submitted, STUDY_VERSION, paper_id, presentation_period,
        question_category, started_at, submitted, response_ms, presentation_order,
    )
    columns = (
        "response_key, session_id, phase, topic, condition_name, stage, item_id, component, answer_json, confidence, correctness, response_time_seconds, recorded_at, "
        "study_version, paper_id, presentation_period, question_category, response_started_at, response_submitted_at, response_time_ms, presentation_order"
    )
    with connection() as database:
        database.execute("DELETE FROM responses_v2 WHERE response_key = " + db_placeholder(), (key,))
        database.execute(
            f"INSERT INTO responses_v2 ({columns}) VALUES ({', '.join(db_placeholder() for _ in values)})",
            values,
        )
        if component == "answer":
            database.execute("UPDATE item_timing_v4 SET submitted_at = " + db_placeholder() + " WHERE response_key = " + db_placeholder(), (submitted, key))
        database.execute("UPDATE study_sessions_v2 SET last_activity_at = " + db_placeholder() + " WHERE session_id = " + db_placeholder(), (submitted, participant_id))
    event_type = "pretest_answer" if stage == "pretest" else "quiz_answer" if stage.endswith("_quiz") else "response_saved"
    log_event(participant_id, event_type, paper_id=paper_id, condition=condition, metadata={"item_id": item_id, "component": component, "response_time_ms": response_ms})


def fetch_responses(participant_id: str, stage: Optional[str] = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM responses_v2 WHERE session_id = ? AND study_version = ?"
    params: list[Any] = [participant_id, STUDY_VERSION]
    if stage:
        query += " AND stage = ?"
        params.append(stage)
    query += " ORDER BY recorded_at, item_id, component"
    with connection() as database:
        rows = database.execute(db_query(query), params).fetchall()
    return [dict(row) for row in rows]


def log_chat_message(
    participant_id: str, period: int, paper_id: str, condition: str, turn_number: int,
    role: str, message_text: str, *, mentor_stage: Optional[str] = None,
    latency_ms: Optional[int] = None, provider: Optional[str] = None,
    model: Optional[str] = None, retry_count: int = 0,
    error_status: Optional[str] = None, prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> str:
    message_id = str(uuid.uuid4())
    now = utc_now_iso()
    values = (
        message_id, participant_id, period, condition, turn_number, role, message_text,
        now, None if latency_ms is None else latency_ms / 1000, provider, model,
        PROMPT_VERSION, retry_count, error_status, prompt_tokens, completion_tokens,
        STUDY_VERSION, paper_id, mentor_stage, latency_ms, error_status,
    )
    columns = (
        "event_id, session_id, phase, condition_name, turn_index, role, content, recorded_at, latency_seconds, provider, model, prompt_version, retry_count, error_text, prompt_tokens, completion_tokens, study_version, paper_id, mentor_stage, latency_ms, error_status"
    )
    with connection() as database:
        database.execute(
            f"INSERT INTO chat_events_v2 ({columns}) VALUES ({', '.join(db_placeholder() for _ in values)})",
            values,
        )
    event_type = "tutor_user_message" if role == "user" else "tutor_ai_response" if role == "assistant" else "error" if role == "error" else "mentor_stage_start"
    log_event(participant_id, event_type, paper_id=paper_id, condition=condition, metadata={"message_id": message_id, "mentor_stage": mentor_stage, "turn_number": turn_number})
    return message_id


def fetch_chat(participant_id: str, period: int) -> list[dict[str, Any]]:
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM chat_events_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder() +
            " AND phase = " + db_placeholder() + " ORDER BY turn_index, recorded_at",
            (participant_id, STUDY_VERSION, period),
        ).fetchall()
    return [dict(row) for row in rows]


def update_tutor_metrics(participant_id: str, paper_id: str) -> None:
    with connection() as database:
        rows = database.execute(
            "SELECT role, content FROM chat_events_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder() + " AND paper_id = " + db_placeholder() + " AND error_status IS NULL",
            (participant_id, STUDY_VERSION, paper_id),
        ).fetchall()
    users = [str(row["content"]) for row in rows if row["role"] == "user"]
    assistants = [str(row["content"]) for row in rows if row["role"] == "assistant"]
    _update_metrics(participant_id, paper_id, {
        "number_of_user_turns": len(users), "number_of_ai_turns": len(assistants),
        "participant_word_count": sum(len(text.split()) for text in users),
        "assistant_word_count": sum(len(text.split()) for text in assistants),
    })


def tutor_requirement_met(participant_id: str, paper_id: str, condition: str) -> bool:
    metrics = get_paper_metrics(participant_id, paper_id) or {}
    if condition == "structured":
        return bool(metrics.get("mentor_fidelity_complete"))
    return int(metrics.get("number_of_user_turns") or 0) >= 1 and int(metrics.get("number_of_ai_turns") or 0) >= 1


def current_mentor_stage(participant_id: str, paper_id: str) -> str:
    metrics = get_paper_metrics(participant_id, paper_id) or {}
    return str(metrics.get("mentor_stage") or MENTOR_STAGES[0])


def complete_mentor_stage(participant_id: str, paper_id: str, stage: str, condition: str) -> str:
    if stage not in MENTOR_STAGES:
        raise ValueError("Unknown mentor stage")
    index = MENTOR_STAGES.index(stage)
    following = MENTOR_STAGES[index + 1] if index + 1 < len(MENTOR_STAGES) else "complete"
    fields = {f"mentor_completed_{stage}": 1, "mentor_stage": following}
    if following == "complete":
        fields["mentor_fidelity_complete"] = 1
    _update_metrics(participant_id, paper_id, fields)
    log_event(participant_id, "mentor_stage_complete", paper_id=paper_id, condition=condition, metadata={"stage": stage, "next_stage": following})
    if following != "complete":
        log_event(participant_id, "mentor_stage_start", paper_id=paper_id, condition=condition, metadata={"stage": following})
    return following


def tutor_error_message(error_status: Optional[str], *, recorded: bool = True) -> str:
    """Safe participant-facing explanation, including historical error formats."""
    code = str(error_status or "").lower()
    if "401" in code or "credentials" in code or "api key expired" in code:
        detail = "The AI service's credentials need attention from the research team. Repeated retries will not resolve this."
    elif "402" in code:
        detail = "The AI service's account needs attention from the research team. Repeated retries will not resolve this."
    elif "empty_response" in code or "incomplete_response" in code:
        detail = "The AI service did not return a complete answer. Please try sending your question again."
    elif "429" in code:
        detail = "The AI service is busy. Please wait briefly and try again."
    elif any(value in code for value in ("400", "403", "404", "422")):
        detail = "The AI service configuration needs attention from the research team."
    else:
        detail = "The AI service could not respond. Please try again or contact the research team if this continues."
    return detail + (" Your message and the failure have been recorded." if recorded else "")


def pending_tutor_error(history: Iterable[dict[str, Any]]) -> Optional[str]:
    """Show only the latest unresolved error; keep the full research log intact."""
    pending = None
    for event in history:
        if event["role"] == "error":
            pending = event.get("error_status") or "provider_error"
        elif event["role"] == "assistant" and not event.get("error_status"):
            pending = None
    return pending


def call_tutor(
    messages: Iterable[dict[str, str]], condition: str, *, mentor_stage: Optional[str] = None,
    next_question: Optional[str] = None,
) -> dict[str, Any]:
    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError(f"Unsupported tutor condition: {condition!r}. Expected one of {sorted(SUPPORTED_CONDITIONS)}.")
    provider = active_provider()
    model = OPENROUTER_MODEL if provider == "openrouter" else OPENAI_MODEL
    system = GENERIC_TUTOR_PROMPT if condition == "generic" else STRUCTURED_TUTOR_PROMPT
    if condition == "structured":
        system += f"\nCurrent stage: {mentor_stage}. "
        if next_question:
            system += f"After concise feedback, ask this exact next question: {next_question}"
        else:
            system += "This is the final stage. Give a concise synthesis after feedback and do not ask another stage question."
    prompt_messages = [{"role": "system", "content": system}, *list(messages)]
    if DEMO_MODE:
        suffix = f" Next, {next_question}" if next_question else " Your reasoning now connects the finding, evidence, limits, and warranted conclusion."
        return {"ok": True, "content": "That is a useful start. Check that the specific evidence supports the scope of your conclusion." + suffix, "provider": "demo", "model": "demo", "retry_count": 0, "latency_ms": 0, "prompt_tokens": None, "completion_tokens": None, "error_status": None}
    api_key = OPENROUTER_API_KEY if provider == "openrouter" else OPENAI_API_KEY
    base_url = OPENROUTER_BASE_URL if provider == "openrouter" else OPENAI_BASE_URL
    if not api_key:
        return {"ok": False, "content": "", "provider": provider, "model": model, "retry_count": 0, "latency_ms": 0, "prompt_tokens": None, "completion_tokens": None, "error_status": "credentials_unavailable"}
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=30.0, max_retries=0)
    started = time.monotonic()
    last_error = ""
    usage = None
    finish_reason = None
    reasoning_tokens = None
    for retry in range(2):
        usage = None
        finish_reason = None
        reasoning_tokens = None
        try:
            kwargs: dict[str, Any] = {"model": model, "messages": prompt_messages, "temperature": OPENAI_TEMPERATURE, "top_p": OPENAI_TOP_P, "max_tokens": V4_TUTOR_MAX_TOKENS}
            if provider == "openrouter":
                kwargs["extra_headers"] = {key: value for key, value in {"HTTP-Referer": OPENROUTER_HTTP_REFERER, "X-OpenRouter-Title": OPENROUTER_APP_TITLE}.items() if value}
                reasoning = tutor_reasoning_config(provider, model)
                if reasoning is not None:
                    kwargs["extra_body"] = {"reasoning": reasoning}
            response = client.chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            reasoning_tokens = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
            choice = response.choices[0] if response.choices else None
            finish_reason = getattr(choice, "finish_reason", None)
            content = getattr(getattr(choice, "message", None), "content", None) or ""
            if not content.strip():
                last_error = "empty_response"
            elif finish_reason in {"length", "content_filter"}:
                last_error = "incomplete_response"
            else:
                client.close()
                return {"ok": True, "content": content, "provider": provider, "model": model, "retry_count": retry, "latency_ms": round((time.monotonic() - started) * 1000), "prompt_tokens": getattr(usage, "prompt_tokens", None), "completion_tokens": getattr(usage, "completion_tokens", None), "error_status": None, "finish_reason": finish_reason, "reasoning_tokens": reasoning_tokens}
        except Exception as exc:
            # Do not persist provider response bodies: they may contain prompts
            # or credentials. Status and exception type suffice for diagnosis.
            status = getattr(exc, "status_code", None)
            last_error = f"http_{status}" if status else type(exc).__name__
            if status is not None and 400 <= status < 500 and status not in {408, 409, 429}:
                break
        if retry == 0:
            time.sleep(1)
    client.close()
    return {"ok": False, "content": "", "provider": provider, "model": model, "retry_count": retry, "latency_ms": round((time.monotonic() - started) * 1000), "prompt_tokens": getattr(usage, "prompt_tokens", None), "completion_tokens": getattr(usage, "completion_tokens", None), "error_status": last_error or "provider_error", "finish_reason": finish_reason, "reasoning_tokens": reasoning_tokens}


def save_post_paper_measures(participant_id: str, paper_id: str, mental_effort: int, predicted_score: int, verification: int) -> None:
    with connection() as database:
        score_row = database.execute(
            "SELECT COALESCE(SUM(correctness), 0) AS score FROM responses_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder() + " AND paper_id = " + db_placeholder() + " AND component = 'answer' AND stage LIKE " + db_placeholder(),
            (participant_id, STUDY_VERSION, paper_id, "%_quiz"),
        ).fetchone()
    actual = int(score_row["score"])
    fields = {
        "mental_effort": int(mental_effort), "predicted_score": int(predicted_score),
        "actual_score": actual, "calibration_signed": int(predicted_score) - actual,
        "calibration_absolute": abs(int(predicted_score) - actual),
        "verification_self_report": int(verification), "measures_completed_at": utc_now_iso(),
    }
    _update_metrics(participant_id, paper_id, fields)
    log_event(participant_id, "post_paper_complete", paper_id=paper_id, metadata=fields)


def advance_stage(session: dict[str, Any], *, timed_out: bool = False) -> dict[str, Any]:
    if session.get("status") not in {ACTIVE_STATUS, "test"}:
        return session
    deadline = parse_iso(session.get("overall_deadline_at"))
    if deadline and deadline <= datetime.now(timezone.utc):
        return mark_timeout(session["session_id"])
    following = next_stage(session["current_stage"])
    if following is None:
        return finalize_session(session["session_id"])
    fields: dict[str, Any] = {"current_stage": following, "stage_started_at": utc_now_iso()}
    if timed_out:
        fields["timeout_count"] = int(session.get("timeout_count") or 0) + 1
    if following == "final_survey":
        fields["final_survey_started_at"] = utc_now_iso()
    update_session(session["session_id"], fields)
    event = "final_survey_start" if following == "final_survey" else "stage_start"
    log_event(session["session_id"], event, condition=session.get("condition_name"), metadata={"stage": following, "timed_out": timed_out})
    return get_session(session["session_id"]) or session


def mark_timeout(participant_id: str, reason: str = "overall_deadline_expired") -> dict[str, Any]:
    update_session(participant_id, {"status": "timeout", "current_stage": "completed", "exclusion_reason": reason, "completion_valid": 0})
    log_event(participant_id, "timeout", metadata={"reason": reason})
    return get_session(participant_id) or {"session_id": participant_id, "status": "timeout"}


def sweep_stale_sessions() -> int:
    initialize_v4_database()
    now = datetime.now(timezone.utc)
    with connection() as database:
        rows = database.execute(
            "SELECT session_id, overall_deadline_at FROM study_sessions_v2 WHERE study_version = " + db_placeholder() + " AND status = " + db_placeholder(),
            (STUDY_VERSION, ACTIVE_STATUS),
        ).fetchall()
    expired = [row["session_id"] for row in rows if (parse_iso(row["overall_deadline_at"]) or now) <= now]
    for participant_id in expired:
        mark_timeout(participant_id)
    return len(expired)


def _completion_reasons(database, session: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    demographics = loads(session.get("demographics_json"), {})
    required_background = {"academic_level", "academic_field", "prior_ai_coursework", "llm_use_frequency", "prior_llm_research_familiarity"}
    if not session.get("consented_at"):
        reasons.append("missing_consent")
    if not required_background.issubset(demographics) or any(demographics.get(key) in (None, "") for key in required_background):
        reasons.append("missing_background")
    rows = database.execute(
        "SELECT stage, item_id, component FROM responses_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder(),
        (session["session_id"], STUDY_VERSION),
    ).fetchall()
    pretest = {row["item_id"] for row in rows if row["stage"] == "pretest" and row["component"] == "answer"}
    if pretest != {item["item_id"] for item in PRETEST_ITEMS}:
        reasons.append("missing_pretest")
    for period in (1, 2):
        assignment = phase_assignment(session, period)
        metrics = database.execute("SELECT * FROM paper_metrics_v4 WHERE metric_key = " + db_placeholder(), (_metric_key(session["session_id"], assignment["paper_id"]),)).fetchone()
        if not metrics or not metrics["reading_finished_at"]:
            reasons.append(f"missing_paper_{period}_reading")
        if not metrics or int(metrics["number_of_user_turns"] or 0) < 1 or int(metrics["number_of_ai_turns"] or 0) < 1:
            reasons.append(f"missing_paper_{period}_tutor")
        if assignment["condition"] == "structured" and (not metrics or not metrics["mentor_fidelity_complete"]):
            reasons.append(f"mentor_fidelity_paper_{period}")
        expected = {item["item_id"] for item in assessment_items(assignment["paper_id"])}
        answered = {row["item_id"] for row in rows if row["stage"] == f"paper_{period}_quiz" and row["component"] == "answer"}
        if answered != expected:
            reasons.append(f"missing_paper_{period}_quiz")
        if not metrics or not metrics["measures_completed_at"]:
            reasons.append(f"missing_paper_{period}_measures")
    final = {row["component"] for row in rows if row["stage"] == "final_survey"}
    if not FINAL_REQUIRED_COMPONENTS.issubset(final):
        reasons.append("missing_final_survey")
    return reasons


def finalize_session(participant_id: str) -> dict[str, Any]:
    initialize_v4_database()
    now = utc_now_iso()
    with connection() as database:
        if using_postgres():
            database.execute("LOCK TABLE study_sessions_v2 IN SHARE ROW EXCLUSIVE MODE")
        else:
            database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT * FROM study_sessions_v2 WHERE session_id = " + db_placeholder() + " AND study_version = " + db_placeholder(),
            (participant_id, STUDY_VERSION),
        ).fetchone()
        if not row:
            raise ValueError("Unknown V4 participant.")
        session = dict(row)
        if session["current_stage"] == "completed":
            return session
        reasons = _completion_reasons(database, session)
        adherence = loads(session.get("adherence_json"), {})
        excluded = list(reasons)
        if adherence.get("prohibited_tool_report") == "Yes":
            excluded.append("prohibited_tool_report")
        if session.get("is_test"):
            status, valid, rank = "test", 0, None
            excluded.append("test")
        elif excluded:
            status, valid, rank = "invalid", 0, None
        else:
            completed = _valid_completion_count(database)
            if completed >= RECRUITMENT_TARGET_COMPLETIONS:
                status, valid, rank = "post_target", 0, None
                excluded.append("post_target")
            else:
                status, valid, rank = "completed", 1, completed + 1
        database.execute(
            "UPDATE study_sessions_v2 SET status = " + db_placeholder() + ", current_stage = 'completed', completed_at = " + db_placeholder() +
            ", final_survey_finished_at = " + db_placeholder() + ", completion_valid = " + db_placeholder() + ", completion_rank = " + db_placeholder() +
            ", exclusion_reason = " + db_placeholder() + ", last_activity_at = " + db_placeholder() + " WHERE session_id = " + db_placeholder(),
            (status, now, now, valid, rank, ",".join(sorted(set(excluded))) or None, now, participant_id),
        )
    log_event(participant_id, "final_survey_complete")
    log_event(participant_id, "study_complete", metadata={"status": status, "completion_valid": valid})
    return get_session(participant_id) or session


def _csv_bytes(rows: list[dict[str, Any]], fieldnames: Optional[list[str]] = None) -> bytes:
    names = fieldnames or (list(rows[0]) if rows else [])
    output = io.StringIO()
    if names:
        writer = csv.DictWriter(output, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def raw_table_csv(table: str) -> bytes:
    if table not in RAW_TABLES:
        raise ValueError("Unsupported V4 raw export table")
    with connection() as database:
        if table == "study_sessions_v2":
            rows = database.execute("SELECT * FROM study_sessions_v2 WHERE study_version = " + db_placeholder(), (STUDY_VERSION,)).fetchall()
        elif table in {"responses_v2", "chat_events_v2"}:
            rows = database.execute(f"SELECT * FROM {table} WHERE study_version = " + db_placeholder(), (STUDY_VERSION,)).fetchall()
        else:
            rows = database.execute(f"SELECT * FROM {table} WHERE study_version = " + db_placeholder(), (STUDY_VERSION,)).fetchall()
    return _csv_bytes([dict(row) for row in rows])


def identity_csv() -> bytes:
    with connection() as database:
        rows = database.execute(
            "SELECT i.session_id AS participant_id, i.participant_name, i.recorded_at FROM participant_identity_v2 i JOIN study_sessions_v2 s ON s.session_id = i.session_id WHERE s.study_version = " + db_placeholder() + " ORDER BY i.recorded_at",
            (STUDY_VERSION,),
        ).fetchall()
    return _csv_bytes([dict(row) for row in rows], ["participant_id", "participant_name", "recorded_at"])


def _participant_records() -> list[dict[str, Any]]:
    with connection() as database:
        sessions = database.execute("SELECT * FROM study_sessions_v2 WHERE study_version = " + db_placeholder() + " ORDER BY overall_started_at", (STUDY_VERSION,)).fetchall()
        metrics = database.execute("SELECT * FROM paper_metrics_v4 WHERE study_version = " + db_placeholder(), (STUDY_VERSION,)).fetchall()
        responses = database.execute("SELECT * FROM responses_v2 WHERE study_version = " + db_placeholder(), (STUDY_VERSION,)).fetchall()
    metric_index: dict[str, list[dict[str, Any]]] = {}
    response_index: dict[str, list[dict[str, Any]]] = {}
    for row in metrics:
        metric_index.setdefault(row["participant_id"], []).append(dict(row))
    for row in responses:
        response_index.setdefault(row["session_id"], []).append(dict(row))
    output = []
    for row in sessions:
        session = dict(row); pid = session["session_id"]
        demo = loads(session.get("demographics_json"), {})
        participant_metrics = sorted(metric_index.get(pid, []), key=lambda item: item["presentation_period"])
        participant_responses = response_index.get(pid, [])
        baseline_rows = [item for item in participant_responses if item["stage"] == "pretest" and item["correctness"] is not None]
        baseline_score = sum(int(item["correctness"]) for item in baseline_rows)
        baseline_started = min((item["response_started_at"] for item in baseline_rows if item.get("response_started_at")), default=None)
        baseline_finished = max((item["response_submitted_at"] for item in baseline_rows if item.get("response_submitted_at")), default=None)
        baseline_duration = _seconds_between(baseline_started, baseline_finished)
        final = {item["component"]: loads(item["answer_json"], None) for item in participant_responses if item["stage"] == "final_survey"}
        scores = [None if item.get("actual_score") is None else int(item["actual_score"]) for item in participant_metrics]
        quiz_rows = [item for item in participant_responses if str(item.get("stage", "")).endswith("_quiz")]
        category_accuracy = {}
        for category in ("central_finding", "methodological_reasoning", "evidence_conclusion", "limitation_uncertainty", "unsupported_inference"):
            values = [int(item["correctness"]) for item in quiz_rows if item.get("question_category") == category and item.get("correctness") is not None]
            category_accuracy[category] = _mean_or_none(values)
        trust_values = [final.get(f"trust_item_{n}") for n in range(1, 4)]
        design_model = session_design_model(session)
        try:
            period_conditions = [phase_assignment(session, period)["condition"] for period in (1, 2)]
            period_papers = [phase_assignment(session, period)["paper_id"] for period in (1, 2)]
        except (KeyError, ValueError):
            period_conditions, period_papers = [None, None], [None, None]
        output.append({
            "participant_id": pid, "study_version": STUDY_VERSION,
            "design_model": design_model,
            "condition": session.get("condition_name"), "sequence_id": session.get("assigned_sequence"),
            "paper_1_id": period_papers[0], "paper_2_id": period_papers[1],
            "paper_1_condition": period_conditions[0], "paper_2_condition": period_conditions[1],
            "paper_order": session.get("paper_order_json"), "status": session.get("status"),
            "is_test": session.get("is_test"), "completion_valid": session.get("completion_valid"),
            "completion_rank": session.get("completion_rank"), "exclusion_reason": session.get("exclusion_reason"),
            "consent_version": session.get("consent_version"), "consent_timestamp": session.get("consented_at"),
            "started_at": session.get("overall_started_at"), "completed_at": session.get("completed_at"),
            "academic_level": demo.get("academic_level"), "academic_field": demo.get("academic_field"),
            "prior_ai_coursework": demo.get("prior_ai_coursework"), "llm_use_frequency": demo.get("llm_use_frequency"),
            "prior_llm_research_familiarity": demo.get("prior_llm_research_familiarity"),
            # baseline_score is the V4 name; pretest_score is retained as a backward-compatible
            # alias so existing analysis code keeps working. Both are the same 0-5 count.
            "baseline_score": baseline_score,
            "baseline_started_at": baseline_started, "baseline_finished_at": baseline_finished,
            "baseline_duration_seconds": baseline_duration,
            "pretest_score": baseline_score,
            "paper_1_score": scores[0] if len(scores) > 0 else None,
            "paper_2_score": scores[1] if len(scores) > 1 else None,
            "overall_post_score": sum(scores) if len(scores) == 2 and None not in scores else None,
            "central_finding_accuracy": category_accuracy["central_finding"],
            "methodology_accuracy": category_accuracy["methodological_reasoning"],
            "evidence_accuracy": category_accuracy["evidence_conclusion"],
            "limitation_accuracy": category_accuracy["limitation_uncertainty"],
            "unsupported_inference_accuracy": category_accuracy["unsupported_inference"],
            # Elapsed time from stage presentation to final submission. All five items render
            # together and Submit rewrites every timestamp, so this is NOT per-item solving time.
            "mean_quiz_stage_elapsed_ms": _mean_or_none([item["response_time_ms"] for item in participant_responses if item["stage"].endswith("_quiz") and item.get("response_time_ms") is not None]),
            "predicted_vs_actual_error": _mean_or_none([item["calibration_signed"] for item in participant_metrics if item.get("calibration_signed") is not None]),
            "absolute_calibration_error": _mean_or_none([item["calibration_absolute"] for item in participant_metrics if item.get("calibration_absolute") is not None]),
            "mean_mental_effort": _mean_or_none([item["mental_effort"] for item in participant_metrics if item.get("mental_effort") is not None]),
            "mean_verification_self_report": _mean_or_none([item["verification_self_report"] for item in participant_metrics if item.get("verification_self_report") is not None]),
            "total_paper_reopens": sum(int(item.get("paper_reopen_count") or 0) for item in participant_metrics),
            "paper_verification_seconds": sum(float(item.get("paper_view_seconds_during_tutor") or 0) for item in participant_metrics),
            "total_user_turns": sum(int(item.get("number_of_user_turns") or 0) for item in participant_metrics),
            "total_tutor_turns": sum(int(item.get("number_of_ai_turns") or 0) for item in participant_metrics),
            "participant_word_count": sum(int(item.get("participant_word_count") or 0) for item in participant_metrics),
            "assistant_word_count": sum(int(item.get("assistant_word_count") or 0) for item in participant_metrics),
            "trust_score": _mean_or_none([value for value in trust_values if isinstance(value, (int, float))]),
            "tutor_helpfulness": final.get("tutor_helpfulness"),
            "noticed_ai_discrepancy": final.get("noticed_ai_discrepancy"),
            "ai_discrepancy_text": final.get("ai_discrepancy_text"),
            "ai_use_strategy_text": final.get("ai_use_strategy_text"),
            "prohibited_tool_report": final.get("prohibited_tool_report"),
            "material_interruption": final.get("material_interruption"),
            "optional_comment": final.get("optional_comment"),
        })
    return output


def _seconds_between(started: Optional[str], finished: Optional[str]) -> Optional[float]:
    """Whole-stage duration in seconds from two stored UTC ISO strings, or None if either is absent."""
    if not started or not finished:
        return None
    try:
        start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max((end - start).total_seconds(), 0.0), 3)


def _mean_or_none(values: list[Any]) -> Optional[float]:
    numeric = [float(value) for value in values if value is not None]
    return round(mean(numeric), 3) if numeric else None


def participant_export_csv() -> bytes:
    return _csv_bytes(_participant_records())


def item_export_csv() -> bytes:
    participants = {row["participant_id"]: row for row in _participant_records()}
    with connection() as database:
        rows = database.execute(
            "SELECT r.*, m.mental_effort, m.predicted_score, m.actual_score, m.calibration_signed, m.calibration_absolute, m.verification_self_report, m.paper_reopen_count, m.paper_view_seconds_during_tutor FROM responses_v2 r LEFT JOIN paper_metrics_v4 m ON m.participant_id = r.session_id AND m.paper_id = r.paper_id WHERE r.study_version = " + db_placeholder() + " AND r.component = 'answer' ORDER BY r.session_id, r.presentation_period, r.presentation_order",
            (STUDY_VERSION,),
        ).fetchall()
    output = []
    for raw in rows:
        row = dict(raw); participant = participants.get(row["session_id"], {})
        output.append({
            "participant_id": row["session_id"], "study_version": STUDY_VERSION,
            "condition": row.get("condition_name") or participant.get("condition"),
            "paper_id": row.get("paper_id"), "presentation_period": row.get("presentation_period"),
            "item_id": row.get("item_id"), "question_category": row.get("question_category"),
            "item_category": row.get("question_category"),
            "design_model": participant.get("design_model"),
            "is_test": participant.get("is_test"), "completion_valid": participant.get("completion_valid"),
            "status": participant.get("status"), "exclusion_reason": participant.get("exclusion_reason"),
            "selected_answer": loads(row.get("answer_json"), None), "correct": row.get("correctness"),
            "response_started_at": row.get("response_started_at"), "response_submitted_at": row.get("response_submitted_at"),
            "stage_elapsed_to_submit_ms": row.get("response_time_ms"),
            "baseline_score": participant.get("baseline_score"), "pretest_score": participant.get("pretest_score"),
            "baseline_duration_seconds": participant.get("baseline_duration_seconds"),
            "prior_ai_coursework": participant.get("prior_ai_coursework"),
            "llm_use_frequency": participant.get("llm_use_frequency"),
            "prior_llm_research_familiarity": participant.get("prior_llm_research_familiarity"),
            "mental_effort": row.get("mental_effort"), "predicted_score": row.get("predicted_score"),
            "actual_score": row.get("actual_score"), "calibration_signed": row.get("calibration_signed"),
            "calibration_absolute": row.get("calibration_absolute"),
            "verification_self_report": row.get("verification_self_report"),
            "paper_reopen_count": row.get("paper_reopen_count"),
            "paper_view_seconds_during_tutor": row.get("paper_view_seconds_during_tutor"),
        })
    return _csv_bytes(output)


def participant_paper_export_csv() -> bytes:
    """One row per participant-paper, derived from existing storage. No duplicated columns are written.

    `paper_reopen_count` is an in-app PDF-toggle proxy, not a verified count of evidence checks.
    `score_percentage` is derived, not stored. Missing scores stay missing.
    """
    participants = {row["participant_id"]: row for row in _participant_records()}
    with connection() as database:
        rows = database.execute(
            "SELECT * FROM paper_metrics_v4 WHERE study_version = " + db_placeholder() +
            " ORDER BY participant_id, presentation_period",
            (STUDY_VERSION,),
        ).fetchall()
    output = []
    for raw in rows:
        row = dict(raw); participant = participants.get(row["participant_id"], {})
        score = row.get("actual_score")
        score = None if score is None else int(score)
        output.append({
            "participant_id": row["participant_id"], "study_version": STUDY_VERSION,
            "condition": row.get("condition_name"), "paper_id": row.get("paper_id"),
            "paper_position": row.get("presentation_period"),
            "design_model": participant.get("design_model"),
            "sequence_id": participant.get("sequence_id"),
            "is_test": participant.get("is_test"), "completion_valid": participant.get("completion_valid"),
            "status": participant.get("status"), "exclusion_reason": participant.get("exclusion_reason"),
            "mcq_score": score,
            "score_percentage": None if score is None else round(100.0 * score / 5.0, 1),
            "predicted_score": row.get("predicted_score"),
            "calibration_signed": row.get("calibration_signed"),
            "calibration_absolute": row.get("calibration_absolute"),
            "mental_effort": row.get("mental_effort"),
            "verification_self_report": row.get("verification_self_report"),
            "reading_time_seconds": row.get("reading_duration_seconds"),
            "chat_time_seconds": row.get("tutor_duration_seconds"),
            "quiz_time_seconds": row.get("quiz_duration_seconds"),
            "user_message_count": row.get("number_of_user_turns"),
            "assistant_message_count": row.get("number_of_ai_turns"),
            "participant_word_count": row.get("participant_word_count"),
            "assistant_word_count": row.get("assistant_word_count"),
            "paper_reopen_count_proxy": row.get("paper_reopen_count"),
            "paper_view_seconds_during_tutor": row.get("paper_view_seconds_during_tutor"),
            "mentor_stage": row.get("mentor_stage"),
            "mentor_fidelity_complete": row.get("mentor_fidelity_complete"),
            "mentor_completed_central_finding": row.get("mentor_completed_central_finding"),
            "mentor_completed_methodology": row.get("mentor_completed_methodology"),
            "mentor_completed_evidence": row.get("mentor_completed_evidence"),
            "mentor_completed_critical_perspective": row.get("mentor_completed_critical_perspective"),
            "mentor_completed_warranted_interpretation": row.get("mentor_completed_warranted_interpretation"),
            "measures_completed_at": row.get("measures_completed_at"),
        })
    return _csv_bytes(output)


def tutor_export_csv() -> bytes:
    with connection() as database:
        rows = database.execute(
            "SELECT event_id AS message_id, session_id AS participant_id, study_version, paper_id, condition_name AS condition, turn_index AS turn_number, role, content AS message_text, mentor_stage, model, provider, prompt_version, recorded_at AS timestamp, latency_ms, retry_count, error_status, prompt_tokens, completion_tokens FROM chat_events_v2 WHERE study_version = " + db_placeholder() + " ORDER BY session_id, phase, turn_index, recorded_at",
            (STUDY_VERSION,),
        ).fetchall()
    return _csv_bytes([dict(row) for row in rows])


def event_export_csv() -> bytes:
    with connection() as database:
        rows = database.execute(
            "SELECT event_id, participant_id, study_version, paper_id, condition_name AS condition, event_type, recorded_at AS timestamp, metadata_json FROM study_events_v4 WHERE study_version = " + db_placeholder() + " ORDER BY participant_id, recorded_at",
            (STUDY_VERSION,),
        ).fetchall()
    return _csv_bytes([dict(row) for row in rows])
