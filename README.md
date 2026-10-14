# TRACE: learner-first LLM mentoring for reading research papers

Source code for the study platform described in:

> Singh, S., Gupta, A., Nguyen, T. V., & Poor, G. M. *From Answers to Evidence: Adaptive
> Learner-First LLM Mentoring for AI Research.* (Under review.)

TRACE (Tutor for Research Analysis, Critique, and Evidence) asks learners to state their own
interpretation of a research paper before the assistant helps. It evaluates each attempt against
a stage rubric, gives feedback that names missing concepts, and escalates help across attempts.
The platform compares TRACE with a self-directed assistant in a counterbalanced crossover design.

This repository contains **code only**. It is the snapshot of the platform release used for data
collection (release `v8`).

## What is here

| Path | Purpose |
|---|---|
| `app.py`, `app_v5.py` | Streamlit participant interface (entry point: `app.py`) |
| `v5_store.py` | Session controller, stage and attempt state, timing, logging |
| `v5_tutor.py` | TRACE mentor and self-directed assistant: prompts, rubric evaluation, help |
| `data/mentor_rubric.py` | Stage rubrics, attempt limits, help options, scaffold levels |
| `data/paper_source_maps.py` | "Where should I look?" source pointers |
| `data/study_v5.py` | Release configuration: model, generation settings, time limits, sequences |
| `data/crossover.py`, `data/study_v4.py` | Instrument definitions (assessment and survey items) |
| `v5_gateway.py` | Same-origin gateway for browser lifecycle events |
| `v5_exports.py`, `v5_workbook.py` | Research exports |
| `migrations/` | Database schema (PostgreSQL or SQLite) |
| `components/` | Paper-viewer and consultation-logging component |
| `scripts/`, `tests/` | Release freezing, smoke and end-to-end checks, unit tests |
| `analysis/` | Planned-analysis scripts for this release |

Earlier app versions (`app_v4_*`, `v4_utils*`) are included only because the current release
imports shared styling and migration helpers from them.

## What is not here

- **Reading materials.** The two research papers participants read are not redistributed.
- **Consent form, IRB protocol, and study documents.**
- **Participant data.** De-identified results will be released separately.

## Running locally

The platform runs once you supply your own reading materials:

1. Python version per `.python-version`; `pip install -r requirements.txt`.
2. Place paper texts and PDFs under `data/papers/v5/`, with a `provenance.json` describing them,
   and a consent PDF at `data/consent/approved_crossover_consent.pdf`.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set an OpenRouter key,
   or set `DEMO_MODE=true` to run without an LLM.
4. Freeze a release with `python scripts/freeze_v5.py`, then run `streamlit run app.py`.

The model and generation settings used in the study are in `data/study_v5.py` (`GENERATION`).
