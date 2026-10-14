from pathlib import Path
import os

_INITIAL_ENV = dict(os.environ)


def read_setting(name: str, default: str = "") -> str:
    # Reading Streamlit secrets can populate os.environ as a side effect. Keep
    # the process environment captured at startup authoritative so a local
    # secrets file cannot silently overwrite deployment or test overrides.
    # HUMAI_* is an explicit process-level override. This remains reliable
    # when Streamlit has already mirrored secrets into os.environ.
    env_value = _INITIAL_ENV.get(f"HUMAI_{name}")
    if env_value is not None:
        return env_value
    env_value = _INITIAL_ENV.get(name)
    if env_value is not None:
        return env_value

    try:
        import streamlit as st

        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def read_bool_setting(name: str, default: str = "false") -> bool:
    return read_setting(name, default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def read_int_setting(name: str, default: int) -> int:
    try:
        return int(read_setting(name, str(default)))
    except (TypeError, ValueError):
        return default


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = Path(read_setting("RESULTS_DIR", str(BASE_DIR / "results"))).resolve()

RESULTS_CSV = Path(
    os.getenv("RESULTS_CSV_PATH", str(RESULTS_DIR / "results.csv"))
).resolve()
EXPERIMENT_DB = Path(
    os.getenv("EXPERIMENT_DB_PATH", str(RESULTS_DIR / "experiment.db"))
).resolve()
DATABASE_URL = read_setting("DATABASE_URL", "")

DEMO_MODE = read_bool_setting("DEMO_MODE", "false")

LLM_PROVIDER = read_setting("LLM_PROVIDER", "auto").strip().lower()
OPENAI_API_KEY = read_setting("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = read_setting("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = read_setting(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
)
OPENROUTER_MODEL = read_setting("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_HTTP_REFERER = read_setting("OPENROUTER_HTTP_REFERER", "")
OPENROUTER_APP_TITLE = read_setting("OPENROUTER_APP_TITLE", "AI Safety Learning Study")

OPENAI_BASE_URL = read_setting("OPENAI_BASE_URL", "")
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_TEMPERATURE = 0.1
OPENAI_TOP_P = 0.1
OPENAI_MAX_TOKENS = 300
# V4 is independent of the frozen legacy-study generation settings.
V4_TUTOR_MAX_TOKENS = max(512, min(8192, read_int_setting("V4_TUTOR_MAX_TOKENS", 2048)))

ADMIN_ACCESS_TOKEN = read_setting("ADMIN_ACCESS_TOKEN", "")

EXPERIMENT_VERSION = read_setting("EXPERIMENT_VERSION", "llm-reading-v3")
CONSENT_VERSION = read_setting("CONSENT_VERSION", "pending-irb-amendment")
PROMPT_VERSION = read_setting("PROMPT_VERSION", "reading-evaluation-v3")
IRB_AMENDMENT_APPROVED = read_bool_setting("IRB_AMENDMENT_APPROVED", "false")
RECRUITMENT_OPEN = read_bool_setting("RECRUITMENT_OPEN", "false")
RECRUITMENT_TARGET_COMPLETIONS = read_int_setting(
    "RECRUITMENT_TARGET_COMPLETIONS", 100
)

# V4 allocation design. "between_subjects" keeps one tutor condition per participant across
# both papers. "within_subjects" gives each participant one structured and one generic paper,
# counterbalancing which paper carries which condition and which comes first.
# Defaults to within_subjects for the new frozen release; the two designs
# must never be pooled. Records store their own design_model so historical rows stay readable.
V4_DESIGN_MODEL = read_setting("V4_DESIGN_MODEL", "within_subjects").strip().lower()

TOTAL_EXPERIMENT_SECONDS = 55 * 60
STAGE_SECONDS = {
    "pretest": 5 * 60,
    "article_1_read": 7 * 60,
    "article_1_tutor": 4 * 60,
    "article_1_assessment": 5 * 60,
    "article_2_read": 7 * 60,
    "article_2_tutor": 4 * 60,
    "article_2_assessment": 5 * 60,
    "article_3_read": 7 * 60,
    "article_3_tutor": 4 * 60,
    "article_3_assessment": 5 * 60,
    "final_survey": 2 * 60,
}

GENERIC_TUTOR_PROMPT = (
    "You are a friendly reading tutor. Use only the article passage supplied by the application. "
    "Explain the article and answer clarification questions directly, accurately, and concisely. "
    "Do not introduce outside facts, reveal or infer assessment answers, or claim to have seen the assessment."
)

EVALUATION_FIRST_TUTOR_PROMPT = (
    "You are an evaluation-first reading tutor. Use only the article passage supplied by the application. "
    "Before giving a direct explanation, guide the learner through four moves: identify the claim, identify "
    "the evidence, state uncertainty or alternatives, and form a warranted conclusion. Ask one focused "
    "question at a time and then give targeted feedback. Do not introduce outside facts, reveal or infer "
    "assessment answers, or claim to have seen the assessment."
)

# Separate release gate prevents inherited legacy recruitment flags opening a new cohort.
CROSSOVER_RECRUITMENT_OPEN = read_bool_setting("CROSSOVER_RECRUITMENT_OPEN", "false")
