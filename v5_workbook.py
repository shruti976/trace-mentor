"""Single .xlsx study-data workbook, organized around the constructs reported in
the paper. NeonDB remains the source of truth; this is a VIEW generated on demand
from the current data via v5_exports.export_data() plus name/demographic joins.

Two modes: restricted (includes participant name on 01_Participants only) and
deidentified (participant_id only). Analysis tabs never depend on names.
"""
import io, json, datetime
from collections import defaultdict
try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    EASTERN = datetime.timezone(datetime.timedelta(hours=-5), "ET")
import v5_store as s
from v5_exports import export_data

# Timestamp columns shown in US Eastern (the database stores UTC).
TIME_COLS = {"assigned_at", "completed_at", "submitted_at", "responded_at", "timestamp", "created_at",
             "started_at", "finished_at", "response_timestamp", "prediction_timestamp", "received_at", "checked_at"}
def _est(v):
    if not isinstance(v, str) or not v: return v
    try: return datetime.datetime.fromisoformat(v).astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception: return v

CAT_COL = {
    "central_finding": "central_finding_correct",
    "methodological_reasoning": "methodological_reasoning_correct",
    "evidence_conclusion": "evidence_conclusion_correct",
    "limitation_uncertainty": "limitation_uncertainty_correct",
    "unsupported_inference": "unsupported_inference_correct",
}
HELP_TYPES = ["explain_question", "explain_feedback", "hint", "example", "source_pointer", "unsure"]
TAB_ORDER = ["00_README", "01_Participants", "02_Performance", "03_Trust_Reliability",
             "04_Experience", "05_Time", "06_Reasoning_Process", "07_Final_Feedback",
             "08_Full_Conversation",
             "90_Raw_Items", "91_Raw_Conversation", "92_Raw_Stage_Attempts",
             "93_Raw_Scaffold_Events", "94_Raw_Consultation", "95_Raw_Timing",
             "96_Raw_LLM_Requests", "99_Data_Dictionary"]


def _kind(r): return "TEST" if r.get("is_test") else "PILOT" if r.get("is_pilot") else "PROD"
def _num(x):
    try: return None if x is None or x == "" else float(x)
    except (TypeError, ValueError): return None
def _secs(a, b):
    try: return round((s.dt(b) - s.dt(a)).total_seconds(), 1)
    except Exception: return None


def _collect(restricted, include, completed_only):
    data = export_data()
    with s.transaction() as db:
        names = {r["participant_id"]: r["name"] for r in s.rows(db, "SELECT participant_id,name FROM v5_identities")}
        bg = {r["participant_id"]: json.loads(r["background_json"]) for r in s.rows(db, "SELECT participant_id,background_json FROM v5_participants")}
    keep = {r["participant_id"] for r in data["roster"] if _kind(r) in include and (not completed_only or r["session_completed"])}
    kf = lambda rows: [r for r in rows if r["participant_id"] in keep]

    roster = kf(data["roster"]); periods = kf(data["periods"]); items = kf(data["items"])
    exch = kf(data["exchanges"]); reqs = kf(data["requests"]); attempts = kf(data["stage_attempts"])
    scaffolds = kf(data["scaffold_events"]); cons = kf(data["consultation_events"])
    trans = kf(data["transitions"]); measures = kf(data["measures"])

    # ---- 01_Participants ----
    participants = []
    for r in roster:
        pid = r["participant_id"]; b = bg.get(pid, {})
        row = {}
        if restricted: row["name"] = names.get(pid)
        row.update(participant_id=pid, participant_type=_kind(r), release_id=r["release_id"], sequence_id=r["sequence_id"],
                   status=r["status"], assigned_at=r["assigned_at"], completed_at=r["completed_at"],
                   academic_level=b.get("academic_level"), academic_field=b.get("academic_field"),
                   prior_ai_coursework=b.get("prior_ai_coursework"), llm_use_frequency=b.get("llm_use_frequency"),
                   prior_llm_research_familiarity=b.get("prior_llm_research_familiarity"),
                   baseline_score=r["baseline_score"],
                   period1_paper=r["period1_paper"], period1_condition=r["period1_condition"], period1_score=r["period1_score"],
                   period2_paper=r["period2_paper"], period2_condition=r["period2_condition"], period2_score=r["period2_score"],
                   complete_pair=r["complete_pair"], session_completed=r["session_completed"])
        fj = json.loads(r["final_json"] or "{}")
        row.update(preferred_condition=fj.get("preferred_condition"), noticed_ai_discrepancy=fj.get("noticed_ai_discrepancy"),
                   material_interruption=fj.get("material_interruption"), prohibited_tool_report=fj.get("prohibited_tool_report"))
        participants.append(row)

    # index helpers
    items_by = defaultdict(list)
    for it in items: items_by[(it["participant_id"], it["period"])].append(it)
    reqs_by = defaultdict(list)
    for q in reqs: reqs_by[(q["participant_id"], q["period"])].append(q)
    trans_by = defaultdict(list)
    for t in trans: trans_by[(t["participant_id"], t["from_stage"])].append(t)
    scaf_by = defaultdict(list)
    for e in scaffolds: scaf_by[(e["participant_id"], e["period"])].append(e)
    scaf_stage = defaultdict(list)
    for e in scaffolds: scaf_stage[(e["participant_id"], e["period"], e["structured_stage"])].append(e)
    att_stage = defaultdict(list)
    for a in attempts:
        if a.get("structured_stage"): att_stage[(a["participant_id"], a["period"], a["structured_stage"])].append(a)

    # ---- 02_Performance / 03_Trust / 04_Experience / 05_Time ----
    performance, trust, experience, time_tab = [], [], [], []
    for p in periods:
        pid, per = p["participant_id"], p["period"]; base = dict(participant_id=pid, sequence_id=p["sequence_id"], period=per, paper_id=p["paper_id"], condition=p["condition"])
        pit = [i for i in items_by[(pid, per)] if i["paper_id"] != "baseline"]
        catcorrect = {c: None for c in CAT_COL.values()}
        for i in pit:
            col = CAT_COL.get(i["category"])
            if col: catcorrect[col] = i["correct"]
        answered = sum(1 for i in pit if i["correct"] is not None)
        actual = p["actual_score"]
        performance.append({**base, "baseline_score": p["baseline_score"], "actual_score": actual,
            "score_percent": (round(100 * actual / 5, 1) if actual is not None else None),
            "predicted_score": p["predicted_score"], "signed_calibration_error": p["signed_calibration_error"],
            "absolute_calibration_error": p["absolute_calibration_error"], **catcorrect,
            "answered_items": answered, "complete_assessment": int(answered == 5)})
        trust.append({**base, "trust_item_1": p["trust_item_1"], "trust_item_2": p["trust_item_2"], "trust_item_3": p["trust_item_3"],
            "trust_mean": p["trust_mean"], "verification_rating": p["verification_rating"],
            "source_consultation_count": p["source_consultation_count"], "source_consultation_seconds": p["source_consultation_seconds"],
            "source_consultation_complete": p["source_consultation_complete"], "consultation_logging_coverage": p["consultation_logging_coverage"],
            "consultation_unclosed_intervals": p["consultation_unclosed_intervals"],
            "noticed_ai_discrepancy": json.loads(next((r["final_json"] for r in roster if r["participant_id"] == pid), "{}")).get("noticed_ai_discrepancy")})
        # help counts
        hc = defaultdict(int)
        for e in scaf_by[(pid, per)]: hc[e["help_type"]] += 1
        experience.append({**base, "mental_effort": p["mental_effort"], "helpfulness": p["helpfulness"],
            "participant_turn_count": p["completed_exchanges"], "assistant_turn_count": p["completed_exchanges"],
            "exchange_count": p["completed_exchanges"], "help_requests_total": sum(hc.values()),
            **{f"{h}_count": hc[h] for h in HELP_TYPES}})
        # time
        def stage_secs(kind):
            ts = trans_by.get((pid, f"{per}_{kind}"), [])
            return round(sum(t["stage_elapsed_seconds"] for t in ts), 1) if ts else None
        reading, tutor, quiz, follow = stage_secs("read"), stage_secs("tutor"), stage_secs("quiz"), stage_secs("followup")
        lat = [_secs(q["started_at"], q["finished_at"]) for q in reqs_by[(pid, per)] if q.get("finished_at")]
        lat = [x for x in lat if x is not None]
        time_tab.append({**base, "reading_seconds": reading, "tutor_seconds": tutor, "assessment_seconds": quiz,
            "followup_seconds": follow, "source_consultation_seconds": p["source_consultation_seconds"],
            "total_period_seconds": round(sum(x for x in (reading, tutor, quiz, follow) if x), 1) if any(x for x in (reading, tutor, quiz, follow)) else None,
            "mean_llm_response_latency_seconds": (round(sum(lat) / len(lat), 2) if lat else None),
            "max_llm_response_latency_seconds": (max(lat) if lat else None),
            "llm_request_count": len(reqs_by[(pid, per)]),
            "llm_retry_count": sum(1 for q in reqs_by[(pid, per)] if (q.get("retry_number") or 0) > 0),
            "llm_error_count": sum(1 for q in reqs_by[(pid, per)] if q["status"] != "success")})

    # ---- 06_Reasoning_Process ----
    reasoning = []
    for (pid, per, stage), atts in sorted(att_stage.items()):
        atts = sorted(atts, key=lambda a: a["attempt_number"])
        p = next((x for x in periods if x["participant_id"] == pid and x["period"] == per), {})
        hc = defaultdict(int)
        for e in scaf_stage[(pid, per, stage)]: hc[e["help_type"]] += 1
        final = atts[-1]
        reasoning.append({"participant_id": pid, "period": per, "paper_id": p.get("paper_id"), "condition": p.get("condition"),
            "structured_stage": stage, "initial_response": atts[0]["learner_response"], "initial_classification": atts[0]["classification"],
            "attempt_count": len(atts), "revision_count": len(atts) - 1, "final_response": final["learner_response"],
            "final_classification": final["classification"], "final_sufficient": final["sufficient"],
            "misconception_observed": int(any(a.get("misconception") for a in atts)),
            "max_hint_level": max((a["hint_level"] for a in atts), default=0), "help_requests_total": sum(hc.values()),
            **{f"{h}_count": hc[h] for h in HELP_TYPES}, "completion_reason": final["completion_reason"],
            "stage_completed": int(final["completion_reason"] is not None)})

    # ---- 07_Final_Feedback ----
    final_fb = []
    for r in roster:
        fj = json.loads(r["final_json"] or "{}")
        final_fb.append({"participant_id": r["participant_id"], "preferred_condition": fj.get("preferred_condition"),
            "assistant_preference": fj.get("assistant_preference"), "noticed_ai_discrepancy": fj.get("noticed_ai_discrepancy"),
            "material_interruption": fj.get("material_interruption"), "prohibited_tool_report": fj.get("prohibited_tool_report"),
            "ai_use_strategy_text": fj.get("ai_use_strategy_text"), "ai_discrepancy_text": fj.get("ai_discrepancy_text"),
            "optional_comment": fj.get("optional_comment"), "completed_at": r["completed_at"]})

    # ---- Raw tabs ----
    raw_items = [{"participant_id": i["participant_id"], "period": i["period"], "paper_id": i["paper_id"], "condition": i["condition"],
        "item_scope": "baseline" if i["paper_id"] == "baseline" else "paper_assessment", "item_id": i["item_id"],
        "category": i["category"], "selected_option_id": i["selected_option_id"], "correct": i["correct"],
        "option_order_json": i["option_order_json"], "stage_elapsed_seconds": i["stage_elapsed_seconds"], "instrument_version": i["instrument_version"]} for i in items]
    raw_conv = [{k: e.get(k) for k in ("exchange_id", "participant_id", "period", "paper_id", "condition", "structured_stage",
        "required_exchange_number", "user_text", "assistant_text", "status", "submitted_at", "completed_at", "model_id", "prompt_version")} for e in exch]
    raw_att = [{k: a.get(k) for k in ("attempt_id", "participant_id", "period", "paper_id", "structured_stage", "required_exchange_number",
        "attempt_number", "learner_response", "classification", "present_concepts_json", "missing_concepts_json", "misconception",
        "sufficient", "hint_level", "tutor_response", "completion_reason", "model_id", "prompt_version", "submitted_at", "responded_at")} for a in attempts]
    raw_scaf = [{k: e.get(k) for k in ("event_id", "participant_id", "period", "paper_id", "structured_stage", "required_exchange_number",
        "event_type", "help_type", "pre_attempt", "scaffold_level", "attempt_number", "pointer_ref", "pointer_paper_id",
        "scaffold_text", "model_id", "prompt_version", "created_at")} for e in scaffolds]
    raw_cons = [{k: e.get(k) for k in ("event_id", "participant_id", "period", "paper_id", "condition", "consultation_session_id",
        "event_type", "timestamp", "received_at", "timestamp_source", "close_reason", "is_inferred")} for e in cons]
    raw_time = [{k: t.get(k) for k in ("participant_id", "event_id", "from_stage", "to_stage", "timestamp", "reason", "stage_elapsed_seconds")} for t in trans]
    raw_req = [{k: q.get(k) for k in ("request_id", "exchange_id", "participant_id", "period", "paper_id", "condition", "retry_number",
        "started_at", "finished_at", "status", "error_status", "model_id", "prompt_version", "usage_json", "provenance_json")} for q in reqs]

    # ---- 08_Full_Conversation (readable, interleaved transcript per participant) ----
    ev = []
    for a in attempts: ev.append((a["participant_id"], a["period"], a.get("submitted_at") or "", "turn", a))
    for e in scaffolds: ev.append((e["participant_id"], e["period"], e.get("created_at") or "", "help", e))
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    _nm = (lambda pid: {"name": names.get(pid)}) if restricted else (lambda pid: {})
    full_conversation = []; turn = 0; last = None
    for pid, per, ts, typ, o in ev:
        if (pid, per) != last: turn = 0; last = (pid, per)
        common = {**_nm(pid), "participant_id": pid, "period": per, "condition": o.get("condition"),
                  "paper_id": o.get("paper_id"), "structured_stage": o.get("structured_stage")}
        if typ == "turn":
            turn += 1
            full_conversation.append({**common, "turn": turn, "speaker": "Participant",
                "message": o.get("learner_response"), "classification": o.get("classification"), "timestamp": o.get("submitted_at")})
            if o.get("tutor_response"):
                full_conversation.append({**common, "turn": turn, "speaker": "AI assistant",
                    "message": o.get("tutor_response"), "classification": "", "timestamp": o.get("responded_at")})
        else:
            full_conversation.append({**common, "turn": turn, "speaker": "Help (" + str(o.get("help_type")) + ")",
                "message": o.get("scaffold_text"), "classification": "", "timestamp": o.get("created_at")})

    counts = {"PROD": sum(1 for r in roster if _kind(r) == "PROD"), "TEST": sum(1 for r in roster if _kind(r) == "TEST"),
        "PILOT": sum(1 for r in roster if _kind(r) == "PILOT"),
        "completed": sum(1 for r in roster if r["session_completed"]), "incomplete": sum(1 for r in roster if not r["session_completed"])}
    return dict(participants=participants, performance=performance, trust=trust, experience=experience, time=time_tab,
                reasoning=reasoning, final_feedback=final_fb, full_conversation=full_conversation,
                raw_items=raw_items, raw_conv=raw_conv, raw_att=raw_att,
                raw_scaf=raw_scaf, raw_cons=raw_cons, raw_time=raw_time, raw_req=raw_req, counts=counts,
                restricted=restricted, include=include, completed_only=completed_only)


def _readme(coll):
    from data import study_v5 as spec
    c = coll["counts"]
    return [[x] for x in [
        "AI Research Reading Study — data export workbook",
        "Generated: " + datetime.datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z") + " (US Eastern)",
        "All timestamps in this workbook are shown in US Eastern time (America/New_York); the database stores UTC.",
        "Release: " + spec.RELEASE_ID,
        "Export mode: " + ("RESTRICTED (includes participant names on 01_Participants)" if coll["restricted"] else "DEIDENTIFIED (participant_id only)"),
        "Included participant types: " + ", ".join(coll["include"]) + ("  |  completed only" if coll["completed_only"] else ""),
        "",
        "DESIGN: randomized, counterbalanced, two-period within-subject crossover.",
        "Each participant experiences BOTH conditions, one per paper:",
        "  Self-Directed = free assistant (answers whatever the learner asks).",
        "  Structured = research mentor with a 5-stage reasoning gate + adaptive help.",
        "Papers: paper_a = 'On the Limitations of LLM-Synthesized Social Media Misinformation Moderation';",
        "        paper_b = 'Exploring Use and Perceptions of Generative AI Art Tools by Blind Artists'.",
        "Sequences: S1 A/self→B/struct; S2 A/struct→B/self; S3 B/self→A/struct; S4 B/struct→A/self.",
        "Participant types: PROD = real; TEST/PILOT = excluded from analysis.",
        "",
        "SCALES: trust items 1–7 (1=strongly disagree). mental_effort 1–9. helpfulness 1–7.",
        "verification_rating 1–5 (self-reported source checking). MCQ score 0–5 per paper.",
        "TIME: all *_seconds are WALL-CLOCK elapsed per stage (the timer runs while away).",
        "Do NOT interpret them as active reading/thinking time.",
        "MISSING VALUES: blank = not collected / stage incomplete / not applicable.",
        "TERMS: source_consultation = paper reopen behavior (NOT proven verification).",
        "noticed_ai_discrepancy = participant PERCEPTION (NOT confirmed hallucination).",
        "",
        f"PARTICIPANTS in this export — PROD: {c['PROD']}  TEST: {c['TEST']}  PILOT: {c['PILOT']}  (completed: {c['completed']}, incomplete/withdrawn: {c['incomplete']}).",
        "Front tabs (01–07) are for analysis; 90–96 are raw audit data; 99 is the data dictionary.",
        "Participant names/identifiers are RESTRICTED data — do not merge names into shared/analysis copies.",
    ]]


DICT = [
    ("02_Performance", "actual_score", "Learning/Performance", "Paper-specific MCQ items answered correctly", "0-5", "participant-period", "v5_responses (sum correct)", "blank = assessment incomplete", ""),
    ("02_Performance", "score_percent", "Learning/Performance", "actual_score as percent of 5", "0-100", "participant-period", "derived", "blank = no score", ""),
    ("02_Performance", "signed_calibration_error", "Metacognition", "predicted_score - actual_score", "-5..5", "participant-period", "v5_predictions/v5_responses", "blank = prediction or score missing", ""),
    ("02_Performance", "absolute_calibration_error", "Metacognition", "abs(predicted - actual)", "0-5", "participant-period", "derived", "", ""),
    ("02_Performance", "<category>_correct", "Learning/Performance", "Correctness (0/1) on each reasoning category item", "0/1", "participant-period", "v5_responses.category", "blank = item unanswered", ""),
    ("03_Trust_Reliability", "trust_mean", "Perceived trust", "Mean of trust_item_1..3", "1-7", "participant-period", "v5_measures", "blank = any trust item missing", "attitudinal trust; keep separate from confidence"),
    ("03_Trust_Reliability", "verification_rating", "Self-reported verification", "How often returned to paper to check the AI", "1-5", "participant-period", "v5_measures", "blank = not answered", "self-report, not observed"),
    ("03_Trust_Reliability", "source_consultation_count", "Observed source consultation", "Participant-initiated paper opens in the tutor stage", "count", "participant-period", "v5_consultation_events", "blank = logging unavailable", "reopen behavior, not proven verification"),
    ("03_Trust_Reliability", "noticed_ai_discrepancy", "Perceived discrepancy", "Did the participant notice AI info inconsistent with the paper", "Yes/No/Unsure", "participant", "final_json", "blank = not answered", "perception, not confirmed hallucination"),
    ("04_Experience", "mental_effort", "Experience", "Self-reported mental effort understanding the paper", "1-9", "participant-period", "v5_measures", "blank = not answered", "cognitive load"),
    ("04_Experience", "helpfulness", "Experience", "Perceived helpfulness of the assistant", "1-7", "participant-period", "v5_measures", "blank = not answered", ""),
    ("04_Experience", "help_requests_total", "Interaction/process", "Total adaptive help-button presses in the stage", "count", "participant-period", "v5_scaffold_events", "0 = none", "process measure, not engagement score"),
    ("05_Time", "reading_seconds", "Time", "Wall-clock seconds in the reading stage", "seconds", "participant-period", "v5_transitions", "blank = stage not reached", "elapsed, not active time"),
    ("05_Time", "tutor_seconds", "Time", "Wall-clock seconds in the tutor stage", "seconds", "participant-period", "v5_transitions", "blank = stage not reached", "elapsed"),
    ("05_Time", "mean_llm_response_latency_seconds", "Time", "Mean model reply latency for the period", "seconds", "participant-period", "v5_requests (finished-started)", "blank = no successful request", ""),
    ("06_Reasoning_Process", "initial_classification", "Reasoning process", "Classification of the learner's FIRST attempt at the stage", "NO_ATTEMPT..MISCONCEPTION", "participant-stage", "v5_stage_attempts", "blank = no attempt", "do not compute learning gain from initial vs final"),
    ("06_Reasoning_Process", "final_sufficient", "Reasoning process", "Whether the accepted final attempt met the stage rubric", "0/1", "participant-stage", "v5_stage_attempts", "", ""),
    ("06_Reasoning_Process", "completion_reason", "Reasoning process", "How the stage completed (sufficient / max_attempts / attempt_cap)", "text", "participant-stage", "v5_stage_attempts", "blank = stage open", ""),
    ("01_Participants", "participant_type", "Sample", "PROD real / TEST / PILOT", "text", "participant", "v5_participants.is_test/is_pilot", "", "TEST/PILOT excluded from analysis"),
    ("01_Participants", "name", "Identifier (RESTRICTED)", "Participant name", "text", "participant", "v5_identities", "restricted export only", "never merge into shared data"),
]


def build_bytes(restricted=False, include=("PROD",), completed_only=False):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    coll = _collect(restricted, include, completed_only)
    wb = Workbook(); wb.remove(wb.active)
    hdr_font = Font(bold=True, color="14213D"); hdr_fill = PatternFill("solid", fgColor="EDF4FF")
    wrap_cols = {"user_text", "assistant_text", "tutor_response", "learner_response", "scaffold_text", "initial_response",
                 "final_response", "provenance_json", "usage_json", "option_order_json", "ai_use_strategy_text",
                 "ai_discrepancy_text", "optional_comment", "message"}

    def sheet(name, rows, cols=None):
        ws = wb.create_sheet(name[:31])
        if name == "00_README":
            for r in rows: ws.append(r)
            ws.column_dimensions["A"].width = 120
            for row in ws.iter_rows():
                for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
            return
        if not rows and not cols: rows = [{}]
        cols = cols or list(dict.fromkeys(k for r in rows for k in r))
        ws.append(cols)
        for c in ws[1]: c.font = hdr_font; c.fill = hdr_fill
        def _cell(c, v):
            if v is None or v == "": return ""
            if c in TIME_COLS: return _est(v)
            return v if isinstance(v, (int, float)) else str(v)
        for r in rows:
            ws.append([_cell(c, r.get(c)) for c in cols])
        ws.freeze_panes = "A2"
        if rows: ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows)+1}"
        for i, col in enumerate(cols, 1):
            L = get_column_letter(i)
            if col in wrap_cols:
                ws.column_dimensions[L].width = 60
                for cell in ws[L][1:]: cell.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                ws.column_dimensions[L].width = min(max(len(col) + 2, 10), 26)

    sheet("00_README", _readme(coll))
    sheet("01_Participants", coll["participants"])
    sheet("02_Performance", coll["performance"])
    sheet("03_Trust_Reliability", coll["trust"])
    sheet("04_Experience", coll["experience"])
    sheet("05_Time", coll["time"])
    sheet("06_Reasoning_Process", coll["reasoning"])
    sheet("07_Final_Feedback", coll["final_feedback"])
    sheet("08_Full_Conversation", coll["full_conversation"])
    sheet("90_Raw_Items", coll["raw_items"])
    sheet("91_Raw_Conversation", coll["raw_conv"])
    sheet("92_Raw_Stage_Attempts", coll["raw_att"])
    sheet("93_Raw_Scaffold_Events", coll["raw_scaf"])
    sheet("94_Raw_Consultation", coll["raw_cons"])
    sheet("95_Raw_Timing", coll["raw_time"])
    sheet("96_Raw_LLM_Requests", coll["raw_req"])
    sheet("99_Data_Dictionary", [dict(zip(
        ["sheet", "column_name", "construct", "description", "unit_or_scale", "level", "source_table_or_derivation", "missing_value_meaning", "notes"], d)) for d in DICT])
    wb.active = 0  # sheets were created in TAB_ORDER already
    out = io.BytesIO(); wb.save(out); return out.getvalue(), coll["counts"]
