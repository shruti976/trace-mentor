"""Participant and restricted researcher interface for the EAAI V4 study."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from archive_utils import build_archive_bytes
from config import ADMIN_ACCESS_TOKEN, DEMO_MODE
from data.crossover import (
    FINAL_SURVEY_ITEMS, FINAL_SURVEY_TEXT, MENTOR_QUESTIONS, MENTOR_STAGES,
    PAPERS, POST_PAPER_SURVEY, BASELINE_INSTRUCTIONS, BASELINE_ITEMS, PRETEST_ITEMS, PROMPT_VERSION, SEQUENCES,
    STRUCTURED_OPENING, STUDY_VERSION, assessment_items, tutor_paper_context,
    RELEASE_ID, CONSENT_PATH, instrument_snapshot,
)
from v4_utils import (
    ACTIVE_SEQUENCES, MIN_READING_SECONDS, RecruitmentClosed, advance_stage, allocation_counts, call_tutor,
    complete_mentor_stage, current_mentor_stage, dumps, ensure_item_started,
    enroll_participant, event_export_csv, fetch_chat, fetch_responses,
    finalize_session, finish_paper_stage, get_paper_metrics, get_session,
    identity_csv, initialize_v4_database, item_export_csv, loads,
    log_chat_message, log_event, mark_timeout, participant_export_csv,
    participant_paper_export_csv,
    model_config, pending_tutor_error, phase_assignment, raw_table_csv, recruitment_summary,
    save_post_paper_measures, save_response, set_paper_view,
    stage_elapsed_seconds, stage_seconds_left, start_paper_stage,
    sweep_stale_sessions, tutor_error_message, tutor_export_csv, tutor_requirement_met,
    update_session, update_tutor_metrics,
)


STAGE_LABELS = {
    "pretest": "Baseline Assessment", "paper_1_read": "Paper 1",
    "paper_1_tutor": "AI Assistant", "paper_1_quiz": "Questions",
    "paper_1_measures": "Paper 1 follow-up", "paper_2_read": "Paper 2",
    "paper_2_tutor": "AI Assistant", "paper_2_quiz": "Questions",
    "paper_2_measures": "Paper 2 follow-up", "final_survey": "Final Survey",
    "completed": "Complete",
}
ACTIVE_STAGES = [stage for stage in STAGE_LABELS if stage != "completed"]
APP_ROOT = Path(__file__).resolve().parent


def rerun() -> None:
    st.rerun() if hasattr(st, "rerun") else st.experimental_rerun()


def query_value(name: str) -> Optional[str]:
    value = st.query_params.get(name)
    return value[0] if isinstance(value, list) and value else value


def apply_style() -> None:
    st.set_page_config(page_title="AI Research Reading Study", page_icon="📘", layout="wide", initial_sidebar_state="collapsed")
    st.markdown("""<style>
    :root{color-scheme:light}.stApp{background:linear-gradient(180deg,#f4f8ff 0,#fff 22rem);color:#15233b}.block-container{max-width:1240px;padding-top:3.5rem;padding-bottom:4rem}[data-testid="stHeader"]{background:transparent}#MainMenu,footer{visibility:hidden}*{box-sizing:border-box}:focus-visible{outline:3px solid #1d4ed8!important;outline-offset:3px!important}
    .study-kicker,.module-kicker{font-size:.76rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#1d4ed8}.study-title{font-size:2.3rem;line-height:1.15;font-weight:850;color:#14213d;margin:.2rem 0}.study-subtitle{color:#40516a;line-height:1.55;margin-bottom:1rem}
    .welcome-card,.module-card{border:1px solid #a9bddf;border-radius:16px;padding:1.2rem 1.35rem;margin:.5rem 0 1rem;background:#edf4ff;color:#26374f}.welcome-card h2,.module-card h2{font-size:1.55rem;line-height:1.25;margin:.2rem 0 .4rem;color:#14213d}
    .study-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin:.8rem 0 1.25rem}.study-fact{border:1px solid #c7d4e5;border-radius:12px;padding:.8rem;background:#fff;color:#334155}.study-fact b{display:block;color:#154f91;margin-bottom:.15rem}.privacy-note,.tutor-note{border-left:4px solid #16705b;border-radius:8px;padding:.8rem .95rem;background:#effaf7;color:#24483f;margin:.55rem 0 1rem}
    .reading-shell{border:1px solid #cbd7e7;border-radius:14px;background:#fff;padding:1.15rem 1.3rem;margin:.8rem 0;color:#26374f;box-shadow:0 3px 14px rgba(30,64,175,.06)}.reading-section{padding:.3rem 0 .75rem;border-bottom:1px solid #e2e8f0;background:#fff;color:#334155}.reading-section:last-child{border-bottom:0}.reading-section h3{font-size:1.08rem;color:#14213d;margin:.5rem 0 .25rem}.reading-section div{line-height:1.65;color:#334155;background:#fff}
    .paper-pane-marker,.chat-pane-marker{height:1px;width:100%;background:transparent}.pane-label{font-size:.76rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#52627a;margin:.2rem 0}.pdf-note{font-size:.82rem;color:#40516a;margin:.2rem 0 .6rem}
    .source-card{border:1px solid #9eb5d8;border-radius:10px;padding:.8rem .95rem;background:#f6f9fd;color:#334155;margin:.65rem 0}.source-card b{color:#14213d}.source-card a{color:#154f91;font-weight:700}.question-card{border:1px solid #b8c5d6;border-left:5px solid #2563eb;border-radius:10px;padding:.9rem 1rem;margin:1rem 0 .45rem;background:#fff;color:#14213d}.question-kind{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:#52627a;margin-bottom:.25rem}
    .stage-strip{position:sticky;top:.35rem;z-index:999;border:1px solid #9eb5d8;border-radius:12px;background:#ffffffee;backdrop-filter:blur(8px);padding:.65rem .8rem;margin:.5rem 0 1rem;box-shadow:0 4px 18px rgba(20,33,61,.12);color:#14213d}.stage-row{display:flex;gap:.7rem;align-items:center;justify-content:space-between;flex-wrap:wrap}.stage-main{font-weight:800}.stage-meta{font-size:.78rem;color:#40516a}.stage-time{font-variant-numeric:tabular-nums;font-weight:800;color:#154f91}.stage-track{height:6px;background:#dce7f5;border-radius:20px;margin-top:.5rem;overflow:hidden}.stage-fill{height:100%;background:#2563eb}
    .completion-card{border:2px solid #16705b;border-radius:18px;padding:1.4rem;text-align:center;background:#effbf7;color:#21463e;margin:1rem 0}.completion-card strong{display:block;font-size:1.3rem;color:#125b4b}@media(max-width:700px){.block-container{padding:3.5rem .75rem 3rem}.study-title{font-size:1.72rem}.welcome-card h2,.module-card h2{font-size:1.28rem}.study-facts{grid-template-columns:1fr}.stage-meta{width:100%;font-size:.7rem}.reading-shell{padding:.9rem}}
    </style>""", unsafe_allow_html=True)


def render_admin() -> None:
    initialize_v4_database()
    with st.sidebar.expander("Researcher access", expanded=False):
        if not st.session_state.get("admin_authorized"):
            token = st.text_input("Admin passphrase", type="password", key="admin_passphrase")
            if st.button("Unlock exports"):
                if ADMIN_ACCESS_TOKEN and hmac.compare_digest(token, ADMIN_ACCESS_TOKEN):
                    st.session_state["admin_authorized"] = True
                    st.session_state.pop("admin_passphrase", None); rerun()
                st.error("Access denied.")
            return
        st.success("Restricted V4 exports unlocked for this browser session.")
        st.warning("Names are restricted. Review chat and free-text exports for identifying details before public sharing.")
        from scripts.migrate_v4 import stored_backup
        backup = stored_backup()
        if backup:
            st.download_button("Download pre-crossover migration backup", backup, "pre-crossover-backup.zip", "application/zip")
        if st.button("Lock researcher access"):
            for key in ("admin_authorized", "admin_backup", "admin_backup_token"):
                st.session_state.pop(key, None)
            rerun()
        st.caption("Provider check sends only a fixed question and public paper summary. It creates no participant or study-response records.")
        if st.button("Check live AI connection", width="stretch"):
            with st.spinner("Checking the configured AI service…"):
                result = call_tutor([
                    {"role": "user", "content": tutor_paper_context("paper_a")},
                    {"role": "user", "content": "In one sentence, what is this paper about?"},
                ], "generic")
            if result["ok"]:
                label = "Demo only — no live provider called" if result["provider"] == "demo" else "Live AI connection verified"
                st.success(label)
                st.write(result["content"])
            else:
                st.error(tutor_error_message(result.get("error_status"), recorded=False))
            st.json({key: result.get(key) for key in ("provider", "model", "error_status", "finish_reason", "reasoning_tokens", "completion_tokens", "latency_ms")})
        with st.expander("Allocation balance"):
            counts = allocation_counts()
            st.caption(f"Design: {counts['design_model']}. Consented non-test V4 assignments under this design only — designs are never pooled.")
            st.write({"condition totals (participant-papers)": counts["conditions"], "total assigned": counts["total_assigned"], "max cell imbalance": counts["max_cell_imbalance"]})
            st.table([
                {"sequence": sequence_id, "paper order": " → ".join(cell["paper_order"]), "condition order": " → ".join(cell["condition_order"]), "assigned": cell["assigned"]}
                for sequence_id, cell in counts["cells"].items()
            ])
        for label, payload, filename in (
            ("Participant-level V4 CSV", participant_export_csv(), "v4_participants.csv"),
            ("Participant-paper V4 CSV", participant_paper_export_csv(), "v4_participant_papers.csv"),
            ("Item-level V4 CSV", item_export_csv(), "v4_items.csv"),
            ("Tutor-message V4 CSV", tutor_export_csv(), "v4_tutor_messages.csv"),
            ("Event-level V4 CSV", event_export_csv(), "v4_events.csv"),
        ):
            st.download_button(label, payload, filename, "text/csv", width="stretch")
        with st.expander("Restricted raw V4 data"):
            for table in ("study_sessions_v2", "responses_v2", "chat_events_v2", "paper_metrics_v4", "item_timing_v4", "study_events_v4"):
                st.download_button(table, raw_table_csv(table), f"v4_{table}.csv", "text/csv", width="stretch")
            st.download_button("Identified V4 roster", identity_csv(), "v4_identified_roster.csv", "text/csv", width="stretch")
        if st.button("Prepare complete backup ZIP", width="stretch"):
            data, _, token = build_archive_bytes(experiment_version=STUDY_VERSION, prompt_version=PROMPT_VERSION)
            st.session_state["admin_backup"], st.session_state["admin_backup_token"] = data, token
        if st.session_state.get("admin_backup"):
            st.download_button("Download complete backup ZIP", st.session_state["admin_backup"], "humanai-study-backup.zip", "application/zip", width="stretch")
            st.caption("Manifest: " + st.session_state["admin_backup_token"][:16] + "…")


def bootstrap() -> Optional[dict[str, Any]]:
    initialize_v4_database(); sweep_stale_sessions()
    participant_id = query_value("participant_id") or query_value("session_id")
    return get_session(participant_id) if participant_id else None


def paper_period(stage: str) -> Optional[int]:
    try:
        return int(stage.split("_")[1]) if stage.startswith("paper_") else None
    except (IndexError, ValueError):
        return None


def format_time(seconds: int) -> str:
    minutes, remaining = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remaining:02d}"


def render_site_header() -> None:
    st.markdown('<div class="study-kicker">Human–AI Learning Research</div>', unsafe_allow_html=True)
    st.markdown('<div class="study-title">📘 AI Research Reading Study</div>', unsafe_allow_html=True)
    st.markdown('<div class="study-subtitle">Read two short AI research papers, use an AI research assistant, and answer independent questions · approximately 35–40 minutes (45-minute limit)</div>', unsafe_allow_html=True)
    st.caption("Save your session URL to resume after a refresh. The timer continues while you are away.")
    if DEMO_MODE:
        st.info("Researcher test mode is active. This session is marked as test data and AI responses are simulated.")


@st.fragment(run_every=2)
def stage_header(participant_id: str) -> None:
    record = get_session(participant_id)
    if not record or record["status"] not in {"active", "test"} or record["current_stage"] == "completed":
        return
    left = stage_seconds_left(record)
    index = ACTIVE_STAGES.index(record["current_stage"]) if record["current_stage"] in ACTIVE_STAGES else 0
    progress = round(100 * index / len(ACTIVE_STAGES))
    st.markdown(f'<div class="stage-strip"><div class="stage-row"><span class="stage-main">Step {index + 1} of {len(ACTIVE_STAGES)} · {escape(STAGE_LABELS[record["current_stage"]])}</span><span class="stage-time" aria-label="Stage time remaining">{format_time(left)}</span><span class="stage-meta">Participant {escape(record["session_id"])}</span></div><div class="stage-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{progress}"><div class="stage-fill" style="width:{progress}%"></div></div></div>', unsafe_allow_html=True)
    if left <= 0:
        current = get_session(participant_id)
        if not current or current["status"] not in {"active", "test"}:
            return
        if deadline_passed(current): mark_timeout(participant_id)
        else: advance_stage(current, timed_out=True)
        rerun()


def deadline_passed(record: dict[str, Any]) -> bool:
    try:
        deadline = datetime.fromisoformat(record["overall_deadline_at"])
        if deadline.tzinfo is None: deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline <= datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return False


def render_onboarding() -> None:
    researcher_test = DEMO_MODE or bool(st.session_state.get("admin_authorized"))
    recruitment = recruitment_summary(); enrollment_open = recruitment["open"] or researcher_test
    st.markdown('<div class="welcome-card"><div class="module-kicker">Introduction</div><h2>Read carefully. Ask questions. Interpret the evidence.</h2><p>This study examines how different forms of AI assistance support the reading and understanding of artificial intelligence research papers. You will read two short research papers, interact with an AI research assistant, and answer questions about each paper. No computer-science background is required.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="study-facts"><div class="study-fact"><b>⏱ About 35–40 minutes</b><span>Complete in one session</span></div><div class="study-fact"><b>📚 Two papers</b><span>Order is assigned automatically</span></div><div class="study-fact"><b>🧠 Independent questions</b><span>Five after each paper</span></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="privacy-note"><b>Before you begin:</b> The approved consent form is provided by the research team. Your name is stored separately from study responses. No response record is created until you select <b>Begin the Study</b>.</div>', unsafe_allow_html=True)
    if not enrollment_open: st.warning("Enrollment is currently closed. Previously enrolled students can resume their saved session.")
    st.download_button("Read or download the consent form", CONSENT_PATH.read_bytes(), "study_consent.pdf", "application/pdf", width="stretch")
    st.caption("Please read the consent form before agreeing below. Save your session link after enrollment if you may need to refresh.")
    if researcher_test: st.info("Researcher test: this session will be excluded from recruitment and analysis. " + ("AI responses are simulated." if DEMO_MODE else "The configured live AI service will be used."))
    participant_name = st.text_input("Full name (required)", key="participant_name")
    age_eligible = st.checkbox("I am at least 18 years old and eligible for this study.", key="age_eligible")
    consent = st.checkbox("I received and read the approved consent form and voluntarily agree to participate.", key="consent")
    academic_level = st.selectbox("Academic level (required)", ["", "Undergraduate", "Master's", "PhD", "Other"], key="academic_level")
    academic_field = st.selectbox("Department or broad academic field (required)", ["", "Computing/engineering", "Natural sciences", "Social sciences", "Humanities/arts", "Business", "Education", "Other"], key="academic_field")
    prior_ai_coursework = st.selectbox("Prior AI coursework (required)", ["", "None", "One course", "Two or more courses"], key="prior_ai_coursework")
    llm_use_frequency = st.selectbox("How often do you use tools such as ChatGPT, Gemini, Claude, or similar LLM-based assistants for academic work? (required)", ["", "Daily", "Several times per week", "Weekly", "Monthly", "Rarely", "Never"], key="llm_use_frequency")
    prior_familiarity = st.selectbox("How familiar are you with research on large language models (LLMs)? (required)", ["", "1 = Not at all familiar", "2", "3", "4", "5 = Very familiar"], key="prior_llm_research_familiarity")
    forced = st.selectbox("Researcher test sequence", list(ACTIVE_SEQUENCES), key="test_sequence") if researcher_test else None
    complete = bool(participant_name.strip() and age_eligible and consent and academic_level and academic_field and prior_ai_coursework and llm_use_frequency and prior_familiarity)
    if st.button("Begin the Study", disabled=not (complete and enrollment_open), width="stretch", type="primary"):
        demographics = {"academic_level": academic_level, "academic_field": academic_field, "prior_ai_coursework": prior_ai_coursework, "llm_use_frequency": llm_use_frequency, "prior_llm_research_familiarity": int(str(prior_familiarity)[0])}
        try: record = enroll_participant(participant_name, demographics, is_test=researcher_test, forced_sequence=forced)
        except (RecruitmentClosed, ValueError) as exc: st.warning(str(exc)); return
        st.query_params["participant_id"] = record["session_id"]; rerun()


def frozen_instrument(record):
    return loads(record.get("instrument_json"), instrument_snapshot())


def display_options(record, item):
    order = loads(record.get("option_order_json"), {}).get(item["item_id"], item["option_ids"])
    labels = dict(zip(item["option_ids"], item["answer_options"]))
    return [labels[option_id] for option_id in order]


def selected_id(item, answer):
    return item["option_ids"][item["answer_options"].index(answer)]


def summary_context(paper):
    return "Study summary only; full PDF is not in context.\nPaper ID: " + paper["paper_id"] + "\n" + paper["citation"] + "\n\n" + "\n\n".join(h+"\n"+t for h,t in paper["display_content"])


def save_pretest_item(record: dict[str, Any], item: dict[str, Any], order: int) -> None:
    answer = st.session_state.get(f"pre_{item['item_id']}")
    if answer is not None:
        save_response(record["session_id"], "pretest", item["item_id"], "answer", answer, question_category=item["question_category"], presentation_order=order, correctness=answer == item["correct_answer"], selected_option_id=selected_id(item, answer))


def render_pretest(record: dict[str, Any]) -> None:
    # Stage key and stored `stage` value remain "pretest" for data continuity; participants
    # only ever see "Baseline Assessment".
    st.subheader("Baseline Assessment")
    st.write(frozen_instrument(record)["baseline_instructions"])
    for order, item in enumerate(frozen_instrument(record)["baseline_items"], 1):
        ensure_item_started(record["session_id"], "pretest", item["item_id"], order)
        st.markdown(f'<div class="question-card"><div class="question-kind">Question {order} of 5</div>{escape(item["question_text"])}</div>', unsafe_allow_html=True)
        st.radio(item["question_text"], display_options(record, item), index=None, key=f"pre_{item['item_id']}", label_visibility="collapsed", on_change=save_pretest_item, args=(record, item, order))
    complete = all(st.session_state.get(f"pre_{item['item_id']}") is not None for item in frozen_instrument(record)["baseline_items"])
    if st.button("Continue to Paper 1", disabled=not complete, width="stretch", type="primary"):
        for order, item in enumerate(frozen_instrument(record)["baseline_items"], 1): save_pretest_item(record, item, order)
        log_event(record["session_id"], "pretest_end", condition=record.get("condition_name"))
        advance_stage(record); rerun()


def assigned_paper(record: dict[str, Any], period: int) -> tuple[dict[str, Any], str, str]:
    assignment = phase_assignment(record, period)
    return frozen_instrument(record)["papers"][assignment["paper_id"]], assignment["paper_id"], assignment["condition"]


def source_card(paper: dict[str, Any]) -> None:
    pdf_link = f' · <a href="{escape(str(paper["optional_pdf_url"]))}" target="_blank" rel="noopener">Open PDF ↗</a>' if paper.get("optional_pdf_url") else ""
    st.markdown(f'<div class="source-card"><b>{escape(paper["authors"])}</b><br>{escape(paper["venue"])} ({paper["year"]})<br>{escape(paper["citation"])}<br><a href="{escape(paper["source_url"])}" target="_blank" rel="noopener">Open source record ↗</a>{pdf_link}</div>', unsafe_allow_html=True)


def paper_content(paper: dict[str, Any]) -> None:
    sections = "".join(f'<section class="reading-section"><h3>{escape(title)}</h3><div>{escape(body)}</div></section>' for title, body in paper["display_content"])
    st.markdown(f'<article class="reading-shell">{sections}</article>', unsafe_allow_html=True)
    for asset in paper.get("figure_or_table_assets", []):
        if isinstance(asset, str):
            st.image(asset, width="stretch")
        elif isinstance(asset, dict) and asset.get("source"):
            st.image(asset["source"], caption=asset.get("caption"), width="stretch")


def paper_pdf(paper: dict[str, Any], key: str, height: int = 560) -> None:
    """Render the exact supplied PDF locally, with a download fallback."""
    relative_path = paper.get("local_pdf_path")
    if not relative_path:
        st.info("The full paper is available from the source link above.")
        return
    path = (APP_ROOT / str(relative_path)).resolve()
    if APP_ROOT not in path.parents or not path.is_file():
        st.warning("The local paper file is unavailable. Use the source link above.")
        return
    payload = path.read_bytes()
    st.download_button(
        "Download exact paper PDF", payload, file_name=path.name,
        mime="application/pdf", key=f"download_{key}", width="stretch",
    )
    version_parts = tuple(int(part) for part in st.__version__.split(".")[:2])
    if hasattr(st, "pdf") and version_parts >= (1, 62):
        st.pdf(payload, height=height, key=f"pdf_{key}")
        return
    with st.container(height=height, border=True, key=f"pdf_pages_{key}"):
        for page_number, relative_page in enumerate(paper.get("rendered_page_paths", []), 1):
            page_path = (APP_ROOT / relative_page).resolve()
            if APP_ROOT in page_path.parents and page_path.is_file():
                st.image(str(page_path), caption=f"Page {page_number}", width="stretch")


def render_reading(record: dict[str, Any], period: int) -> None:
    paper, paper_id, condition = assigned_paper(record, period); start_paper_stage(record, period, "reading")
    st.markdown(f'<div class="module-card"><div class="module-kicker">Paper {period} of 2</div><h2>{escape(paper["title"])}</h2><div>{escape(paper["authors"])} · {escape(paper["venue"])} ({paper["year"]})</div></div>', unsafe_allow_html=True)
    source_card(paper)
    st.markdown('<div class="pane-label">Exact supplied paper</div>', unsafe_allow_html=True)
    paper_pdf(paper, f"read_{period}", height=620)
    st.markdown('<div class="pane-label">Participant-readable summary</div>', unsafe_allow_html=True)
    st.caption("This summary is a study adaptation. Use the PDF above when you want to check the authors' exact wording, tables, or examples.")
    paper_content(paper)
    finished = st.checkbox("I have finished reading this paper.", key=f"paper_{period}_read_complete")
    minimum = 0 if DEMO_MODE else MIN_READING_SECONDS; remaining = max(0, minimum - int(stage_elapsed_seconds(record)))
    if remaining: st.caption(f"Please spend at least {remaining} more seconds engaging with the paper before continuing.")
    if st.button("Continue to AI Research Assistant", disabled=not (finished and remaining == 0), width="stretch", type="primary"):
        finish_paper_stage(record, period, "reading"); log_event(record["session_id"], "paper_close", paper_id=paper_id, condition=condition, metadata={"initial_read": True}); advance_stage(record); rerun()


def paper_view_changed(record: dict[str, Any], period: int, paper_id: str, condition: str) -> None:
    set_paper_view(record["session_id"], paper_id, condition, bool(st.session_state.get(f"paper_{period}_view_open")))


def submit_tutor_message(record: dict[str, Any], period: int, prompt: str) -> None:
    paper, paper_id, condition = assigned_paper(record, period); history = fetch_chat(record["session_id"], period)
    stage = current_mentor_stage(record["session_id"], paper_id) if condition == "structured" else None
    turn = max((int(event["turn_index"]) for event in history), default=0) + 1
    log_chat_message(record["session_id"], period, paper_id, condition, turn, "user", prompt, mentor_stage=stage)
    conversation = [{"role": "user", "content": summary_context(paper)}]
    conversation.extend({"role": event["role"], "content": event["content"]} for event in history if event["role"] in {"user", "assistant"} and not event.get("error_status"))
    conversation.append({"role": "user", "content": prompt})
    next_question = None
    if stage in MENTOR_STAGES:
        index = MENTOR_STAGES.index(stage); next_question = frozen_instrument(record)["mentor_questions"][MENTOR_STAGES[index + 1]] if index + 1 < len(MENTOR_STAGES) else None
    with st.spinner("AI Research Assistant is responding…"):
        result = call_tutor(conversation, condition, mentor_stage=stage, next_question=next_question, system_prompt=frozen_instrument(record)["generic_prompt" if condition == "generic" else "structured_prompt"], generation_settings=loads(record["model_config_json"], {}))
    log_event(record["session_id"], "tutor_request_result", paper_id=paper_id, condition=condition, metadata={
        "model_config": loads(record["model_config_json"], {}), "ok": result["ok"],
        **{key: result.get(key) for key in ("error_status", "finish_reason", "reasoning_tokens", "retry_count")},
    })
    if result["ok"]:
        log_chat_message(record["session_id"], period, paper_id, condition, turn + 1, "assistant", result["content"], mentor_stage=stage, latency_ms=result.get("latency_ms"), provider=result.get("provider"), model=result.get("model"), retry_count=result.get("retry_count", 0), prompt_tokens=result.get("prompt_tokens"), completion_tokens=result.get("completion_tokens"))
        if condition == "structured" and stage: complete_mentor_stage(record["session_id"], paper_id, stage, condition)
    else:
        log_chat_message(record["session_id"], period, paper_id, condition, turn + 1, "error", "AI response unavailable.", mentor_stage=stage, latency_ms=result.get("latency_ms"), provider=result.get("provider"), model=result.get("model"), retry_count=result.get("retry_count", 0), prompt_tokens=result.get("prompt_tokens"), completion_tokens=result.get("completion_tokens"), error_status=result.get("error_status") or "provider_error")
        update_session(record["session_id"], {"tutor_fidelity_failure": 1})
    update_tutor_metrics(record["session_id"], paper_id); rerun()


def render_tutor(record: dict[str, Any], period: int) -> None:
    paper, paper_id, condition = assigned_paper(record, period); start_paper_stage(record, period, "tutor"); history = fetch_chat(record["session_id"], period)
    if condition == "structured" and not history:
        log_chat_message(record["session_id"], period, paper_id, condition, 0, "system", frozen_instrument(record)["structured_opening"] + "\n\n" + frozen_instrument(record)["mentor_questions"][MENTOR_STAGES[0]], mentor_stage=MENTOR_STAGES[0]); history = fetch_chat(record["session_id"], period)
    st.markdown(f'<div class="module-card"><div class="module-kicker">Paper {period} · AI Research Assistant</div><h2>{escape(paper["short_title"])}</h2><div>Use the paper when needed. The assistant will not be available during the independent questions.</div></div>', unsafe_allow_html=True)
    st.caption("The assistant can discuss the study summary only; it cannot inspect the full PDF or its tables.")
    st.markdown('<nav aria-label="Paper and chat navigation"><a href="#paper-pane">Jump to paper and summary</a> · <a href="#chat-pane">Jump to assistant</a></nav>', unsafe_allow_html=True)
    paper_column, chat_column = st.columns([1.08, 0.92], gap="large")
    with paper_column:
        st.markdown('<div id="paper-pane" class="paper-pane-marker" aria-hidden="true"></div><div class="pane-label">Paper and summary</div>', unsafe_allow_html=True)
        source_card(paper)
        paper_open = st.toggle("Show full paper PDF", key=f"paper_{period}_view_open", on_change=paper_view_changed, args=(record, period, paper_id, condition))
        metrics = get_paper_metrics(record["session_id"], paper_id) or {}
        if not paper_open and metrics.get("paper_reopen_started_at"):
            set_paper_view(record["session_id"], paper_id, condition, False)
        if paper_open:
            st.markdown('<div class="pdf-note">Exact research-team-supplied PDF</div>', unsafe_allow_html=True)
            paper_pdf(paper, f"tutor_{period}", height=520)
        st.markdown('<div class="pane-label">Participant-readable summary</div>', unsafe_allow_html=True)
        paper_content(paper)
    with chat_column:
        st.markdown('<div id="chat-pane" class="chat-pane-marker" aria-hidden="true"></div><div class="pane-label">LLM chat</div>', unsafe_allow_html=True)
        if condition == "generic": st.markdown('<div class="tutor-note">You may use the AI assistant to help you understand the research paper. Ask any questions you would normally ask an AI tool while reading a research paper.</div>', unsafe_allow_html=True)
        for event in history:
            if event["role"] == "system":
                with st.chat_message("assistant"): st.write(event["content"])
            elif event["role"] in {"user", "assistant"}:
                with st.chat_message(event["role"]): st.write(event["content"])
        error = pending_tutor_error(history)
        if error:
            st.error(tutor_error_message(error))
            if st.button("Continue without an AI response", key=f"skip_ai_{period}"):
                from v4_utils import bypass_tutor
                bypass_tutor(record["session_id"], paper_id, condition)
                finish_paper_stage(record, period, "tutor"); advance_stage(record); rerun()
        current_stage = current_mentor_stage(record["session_id"], paper_id) if condition == "structured" else None
        if condition == "generic" or current_stage != "complete":
            label = frozen_instrument(record)["mentor_questions"][current_stage] if condition == "structured" else "Ask about the paper..."
            with st.form(f"tutor_form_{period}", clear_on_submit=True):
                prompt = st.text_area(label, key=f"tutor_prompt_{period}", height=120)
                sent = st.form_submit_button("Send message", width="stretch", type="primary")
            if sent and prompt.strip(): submit_tutor_message(record, period, prompt.strip())
        else: st.success("You have completed the guided research discussion.")
        ready = tutor_requirement_met(record["session_id"], paper_id, condition)
        if not ready: st.info(("Complete all five discussion stages" if condition == "structured" else "Send at least one message and receive one completed response") + " before continuing.")
        if st.button("Continue to independent questions", disabled=not ready, width="stretch", type="primary"):
            if st.session_state.get(f"paper_{period}_view_open"):
                set_paper_view(record["session_id"], paper_id, condition, False); st.session_state[f"paper_{period}_view_open"] = False
            finish_paper_stage(record, period, "tutor"); advance_stage(record); rerun()


def save_quiz_answer(record: dict[str, Any], period: int, item: dict[str, Any], order: int) -> None:
    answer = st.session_state.get(f"q{period}_{item['item_id']}")
    if answer is None: return
    _, paper_id, condition = assigned_paper(record, period)
    save_response(record["session_id"], f"paper_{period}_quiz", item["item_id"], "answer", answer, paper_id=paper_id, condition=condition, presentation_period=period, question_category=item["question_category"], presentation_order=order, correctness=answer == item["correct_answer"], selected_option_id=selected_id(item, answer))


def render_quiz(record: dict[str, Any], period: int) -> None:
    paper, paper_id, _ = assigned_paper(record, period); start_paper_stage(record, period, "quiz")
    st.markdown(f'<div class="module-card"><div class="module-kicker">Paper {period} · Independent questions</div><h2>{escape(paper["short_title"])}</h2><div>The paper and assistant are closed in this app. Close downloaded papers, other tabs, saved chats and outside tools. Answer from your own understanding.</div></div>', unsafe_allow_html=True)
    items = paper["mcqs"]
    for order, item in enumerate(items, 1):
        ensure_item_started(record["session_id"], f"paper_{period}_quiz", item["item_id"], order)
        label = item["question_category"].replace("_", " ").title()
        st.markdown(f'<div class="question-card"><div class="question-kind">{escape(label)} · {order} of 5</div>{escape(item["question_text"])}</div>', unsafe_allow_html=True)
        st.radio(item["question_text"], display_options(record, item), index=None, key=f"q{period}_{item['item_id']}", label_visibility="collapsed", on_change=save_quiz_answer, args=(record, period, item, order))
    complete = all(st.session_state.get(f"q{period}_{item['item_id']}") is not None for item in items)
    if st.button("Submit answers", disabled=not complete, width="stretch", type="primary"):
        for order, item in enumerate(items, 1): save_quiz_answer(record, period, item, order)
        finish_paper_stage(record, period, "quiz"); advance_stage(record); rerun()


def save_measure_selection(record, period):
    from v4_utils import save_partial_measures
    _, paper_id, _ = assigned_paper(record, period)
    mapping = {"mental_effort":f"mental_effort_{period}", "predicted_score":f"predicted_score_{period}",
               "verification_self_report":f"verification_{period}", "assistant_helpfulness":f"helpfulness_{period}"}
    values = {field:st.session_state.get(key) for field,key in mapping.items() if st.session_state.get(key) not in (None, "")}
    save_partial_measures(record["session_id"], paper_id, values)


def render_measures(record: dict[str, Any], period: int) -> None:
    paper, paper_id, _ = assigned_paper(record, period)
    survey = frozen_instrument(record)["post_paper_survey"]
    st.markdown(f'<div class="module-card"><div class="module-kicker">Paper {period} follow-up</div><h2>{escape(paper["short_title"])}</h2><div>Four short questions about your experience.</div></div>', unsafe_allow_html=True)
    mental = st.selectbox(survey["mental_effort"]["question"], [""] + survey["mental_effort"]["options"], format_func=lambda value: "" if value == "" else "1 = Very, very low mental effort" if value == 1 else "5 = Moderate mental effort" if value == 5 else "9 = Very, very high mental effort" if value == 9 else str(value), key=f"mental_effort_{period}", on_change=save_measure_selection, args=(record, period))
    predicted = st.selectbox(survey["predicted_score"]["question"], [""] + survey["predicted_score"]["options"], key=f"predicted_score_{period}", on_change=save_measure_selection, args=(record, period))
    verification = st.selectbox(survey["verification_self_report"]["question"], [""] + survey["verification_self_report"]["options"], format_func=lambda value: "" if value == "" else {1:"1 = Never", 2:"2 = Rarely", 3:"3 = Sometimes", 4:"4 = Often", 5:"5 = Very often"}[value], key=f"verification_{period}", on_change=save_measure_selection, args=(record, period))
    helpful = st.selectbox(survey["assistant_helpfulness"]["question"], [""] + list(range(1,8)), format_func=lambda v: "" if v == "" else "1 = Not at all helpful" if v == 1 else "7 = Extremely helpful" if v == 7 else str(v), key=f"helpfulness_{period}", on_change=save_measure_selection, args=(record, period))
    complete = all(value != "" for value in (mental, predicted, verification, helpful)); label = "Continue to Paper 2" if period == 1 else "Continue to Final Survey"
    if st.button(label, disabled=not complete, width="stretch", type="primary"):
        save_post_paper_measures(record["session_id"], paper_id, int(mental), int(predicted), int(verification), int(helpful)); advance_stage(record); rerun()


def save_final_item(record: dict[str, Any], component: str) -> None:
    value = st.session_state.get(component)
    if value in (None, "") and component not in {"optional_comment", "ai_discrepancy_text", "ai_use_strategy_text"}: return
    save_response(record["session_id"], "final_survey", "final_survey", component, value)
    if component in {"prohibited_tool_report", "material_interruption"}:
        adherence = loads(record.get("adherence_json"), {}); adherence[component] = value
        update_session(record["session_id"], {"adherence_json": dumps(adherence)}); record["adherence_json"] = dumps(adherence)


def render_final_survey(record: dict[str, Any]) -> None:
    st.subheader("Final Survey"); st.caption("For agreement items, 1 = strongly disagree and 7 = strongly agree.")
    for key, item in frozen_instrument(record)["final_survey_items"].items():
        st.selectbox(item["question"], [""] + item.get("scale", []), key=key, on_change=save_final_item, args=(record, key))
    final_text = frozen_instrument(record)["final_survey_text"]
    preference = final_text["assistant_preference"]
    st.selectbox(preference["question"], [""] + preference["options"], key="assistant_preference", on_change=save_final_item, args=(record, "assistant_preference"))
    discrepancy = final_text["noticed_ai_discrepancy"]
    st.selectbox(discrepancy["question"], [""] + discrepancy["options"], key="noticed_ai_discrepancy", on_change=save_final_item, args=(record, "noticed_ai_discrepancy"))
    if st.session_state.get("noticed_ai_discrepancy") == "Yes": st.text_area(final_text["ai_discrepancy_text"]["question"], key="ai_discrepancy_text", on_change=save_final_item, args=(record, "ai_discrepancy_text"))
    st.text_area(final_text["ai_use_strategy_text"]["question"], key="ai_use_strategy_text", on_change=save_final_item, args=(record, "ai_use_strategy_text"))
    for key in ("prohibited_tool_report", "material_interruption"):
        item = final_text[key]
        st.selectbox(item["question"], [""] + item["options"], key=key, on_change=save_final_item, args=(record, key))
    st.text_area(final_text["optional_comment"]["question"], key="optional_comment", on_change=save_final_item, args=(record, "optional_comment"))
    required = list(frozen_instrument(record)["final_survey_items"]) + ["noticed_ai_discrepancy", "assistant_preference", "prohibited_tool_report", "material_interruption"]
    complete = all(st.session_state.get(key) not in (None, "") for key in required)
    if st.button("Submit and finish", disabled=not complete, width="stretch", type="primary"):
        for key in (*required, "ai_discrepancy_text", "ai_use_strategy_text", "optional_comment"): save_final_item(record, key)
        try: finalize_session(record["session_id"])
        except ValueError as exc: st.error("The session could not be finalized: " + str(exc)); return
        rerun()


def hydrate_stage(record: dict[str, Any]) -> None:
    stage = record["current_stage"]; period = paper_period(stage)
    for row in fetch_responses(record["session_id"], stage):
        answer = loads(row.get("answer_json"), None)
        if stage == "pretest": key = f"pre_{row['item_id']}"
        elif period and stage.endswith("_quiz"): key = f"q{period}_{row['item_id']}"
        elif stage == "final_survey": key = row["component"]
        else: continue
        st.session_state.setdefault(key, answer)
    if period and stage.endswith("_measures"):
        _, paper_id, _ = assigned_paper(record, period); metrics = get_paper_metrics(record["session_id"], paper_id) or {}
        for source, target in (("mental_effort", f"mental_effort_{period}"), ("predicted_score", f"predicted_score_{period}"), ("verification_self_report", f"verification_{period}"), ("assistant_helpfulness", f"helpfulness_{period}")):
            if metrics.get(source) is not None: st.session_state.setdefault(target, metrics[source])


def render_completed(record: dict[str, Any]) -> None:
    st.markdown('<div class="completion-card"><div style="font-size:2.3rem">✓</div><strong>AI Research Reading Study complete</strong><span>Your responses have been recorded.</span></div>', unsafe_allow_html=True)
    if record["status"] == "test": st.info("This was a researcher test session and is marked for exclusion from valid recruitment.")
    elif record["status"] in {"invalid", "post_target"}: st.info("Your responses were retained. The research team will apply the documented analysis rules.")
    st.success("Thank you for completing the study. Please do not discuss assessment questions with people who have not participated."); st.caption(f"Participant ID: {record['session_id']}")


def render_ended(record: dict[str, Any]) -> None:
    st.warning("This session has ended. Existing responses have been retained, but no further study data can be submitted."); st.caption(f"Participant ID: {record['session_id']}")


def main() -> None:
    initialize_v4_database()
    existing_id = query_value("participant_id") or query_value("session_id")
    existing = get_session(existing_id) if existing_id else None
    if existing and not existing.get("release_id"):
        from app_v4_legacy import main as legacy_main
        legacy_main()
        return
    apply_style()
    if "admin_token" in st.query_params: del st.query_params["admin_token"]
    render_admin(); record = bootstrap(); render_site_header()
    if record is None: render_onboarding(); return
    if record["current_stage"] == "completed":
        render_completed(record) if record["status"] not in {"timeout", "withdrawn"} else render_ended(record); return
    if record["status"] not in {"active", "test"}: render_ended(record); return
    with st.sidebar.expander("Pause or stop participation"):
        st.write("You may close this tab and return with the same link before the session deadline. The timer continues while away.")
        stop = st.checkbox("I want to end my participation", key="confirm_withdraw")
        if st.button("End participation", disabled=not stop):
            from v4_utils import close_active_stage, utc_now_iso
            close_active_stage(record)
            update_session(record["session_id"], {"status":"withdrawn", "current_stage":"completed", "completion_valid":0, "exclusion_reason":"withdrawn", "completed_at":utc_now_iso()})
            log_event(record["session_id"], "withdrawal"); rerun()
    hydrate_stage(record); stage_header(record["session_id"]); stage = record["current_stage"]; period = paper_period(stage)
    if stage == "pretest": render_pretest(record)
    elif stage == "final_survey": render_final_survey(record)
    elif period and stage.endswith("_read"): render_reading(record, period)
    elif period and stage.endswith("_tutor"): render_tutor(record, period)
    elif period and stage.endswith("_quiz"): render_quiz(record, period)
    elif period and stage.endswith("_measures"): render_measures(record, period)
    else: st.error("Unknown study stage. Please contact the research team.")


if __name__ == "__main__": main()
