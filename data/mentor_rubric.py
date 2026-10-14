"""Configurable per-stage rubrics + adaptive-scaffold policy for the structured mentor.

Hashed into the frozen release manifest (rubric_source_sha256), so evaluation
criteria, scaffold levels, and the deterministic help templates cannot silently
drift. Contains NO assessment items, options, or answer keys, and no paper-specific
answers — only stage reasoning criteria and generic scaffolding text. Paper-specific
source locations live in data/paper_source_maps.py.
"""

# Genuine attempts (PARTIAL/SUBSTANTIVE/MISCONCEPTION) permitted per structured stage
# before the mentor gives concise resolution and allows progression.
MENTOR_MAX_ATTEMPTS = 3
# Hard cap on TOTAL submissions per stage (genuine + non-attempts) — a safety valve so
# repeated junk cannot trap the participant. Non-attempts do not count toward
# MENTOR_MAX_ATTEMPTS but do count toward this cap.
MENTOR_ATTEMPT_HARD_CAP = 8
# Help requests permitted per stage before the UI nudges the learner to answer.
MENTOR_MAX_HELP = 6
# Classifications that count as a genuine reasoning attempt.
GENUINE = ("PARTIAL_ATTEMPT", "SUBSTANTIVE_ATTEMPT", "MISCONCEPTION")

STAGES = (
    "central_finding",
    "methodology",
    "evidence",
    "critical_perspective",
    "warranted_interpretation",
)

# Progressive scaffolding levels (Section 5). Higher = more support.
SCAFFOLD_LEVELS = (
    "open_question",            # 0
    "rephrase",                 # 1  clarify the kind of reasoning expected
    "targeted_hint",            # 2  point toward one relevant concept
    "source_pointer",           # 3  which section/table/figure to inspect
    "partial_scaffold",         # 4  part of the answer structure after repeated attempts
    "instructional_resolution", # 5  concise explanation so the learner is not trapped
)

# Help controls offered in the UI. help_type -> (label, scaffold_level).
PRE_ATTEMPT_HELP = {
    "explain_question": ("Explain the question", 1),
    "hint": ("Give me a hint", 2),
    "source_pointer": ("Where should I look?", 3),
    "unsure": ("I'm not sure", 1),
}
POST_ATTEMPT_HELP = {
    "explain_feedback": ("Explain feedback simply", 1),
    "hint": ("Give me another hint", 2),
    "example": ("Give an example", 4),
    "source_pointer": ("Where should I look?", 3),
}

# Whole-message junk that is deterministically NO_ATTEMPT (checked before the LLM
# evaluator). Compared against the trimmed, lowercased learner message. Short but
# meaningful sentences (e.g. "they interviewed six blind artists") are NOT listed
# and fall through to the LLM evaluator.
NO_ATTEMPT_TOKENS = frozenset({
    "summary", "summarize", "summarise", "methods", "method", "methodology",
    "table", "table 1", "table1", "table 2", "table2", "figure", "results",
    "result", "intro", "introduction", "conclusion", "evidence", "limitations",
    "idk", "i dk", "i don't know", "i dont know", "dont know", "don't know",
    "no idea", "not sure", "unsure", "help", "?", "??", ".", "..", "...",
    "asdf", "asdfgh", "na", "n/a", "none", "nothing", "give me the answer",
    "answer", "the answer", "tell me", "tell me the answer", "what", "iddk",
})

RUBRIC = {
    "central_finding": {
        "label": "Central claim / contribution",
        "criteria": [
            "identifies what the paper studied (topic/question)",
            "states the paper's central finding or main contribution",
        ],
        "sufficient_when": "the learner states, in their own words, both what was studied and the main finding/contribution.",
        "not_this": "naming a topic or typing a section label instead of stating the actual claim.",
        "explain": "I'm asking what the paper is mainly about and what the authors concluded — the single most important takeaway, in your own words. Not every detail, just the core point.",
        "hint": "Think about what problem the authors set out to address, and the one main thing they found or built.",
        "example": "For example, in a different study someone might say: 'The researchers tested whether a reminder app improved medication adherence, and found it helped older adults most.' Now try that shape for this paper.",
    },
    "methodology": {
        "label": "Methodological / evaluation reasoning",
        "criteria": [
            "identifies the relevant participants, data, or method",
            "identifies an important methodological or evaluation decision",
            "where possible, explains why that choice mattered",
        ],
        "sufficient_when": "the learner describes how the study was actually conducted and names a meaningful methodological choice.",
        "not_this": "typing 'methods' or listing a heading without describing what was done.",
        "explain": "I'm asking HOW the researchers tried to answer their question — who or what they studied, what those participants or data did, and how evidence was collected or evaluated.",
        "hint": "Think about who (or what data) took part, and what they were actually asked to do during the study.",
        "example": "For example, in a different study someone might say: 'They interviewed teachers because they wanted detailed accounts of classroom experience.' Now apply that structure to this paper.",
    },
    "evidence": {
        "label": "Supporting evidence",
        "criteria": [
            "identifies a specific result, table, figure, quotation, or observation",
            "connects that evidence to the relevant claim",
        ],
        "sufficient_when": "the learner points to specific evidence in the paper and links it to a conclusion.",
        "not_this": "naming 'table 1' or 'results' without stating what the evidence shows.",
        "explain": "I'm asking for a specific piece of evidence from the paper — a result, table, figure, or observation — and how it supports the authors' conclusion.",
        "hint": "Think about one concrete result the authors report, and what that result actually shows.",
        "example": "For example, in a different study someone might say: 'Table 2 shows the app group scored 15% higher, which supports the claim that reminders help.' Now find the parallel in this paper.",
    },
    "critical_perspective": {
        "label": "Limitations / validity / alternatives",
        "criteria": [
            "identifies a limitation, uncertainty, validity issue, sampling constraint, generalization limit, or alternative explanation",
        ],
        "sufficient_when": "the learner raises a genuine limitation or alternative explanation grounded in the study.",
        "not_this": "saying 'limitations' generically or claiming there are none without reasoning.",
        "explain": "I'm asking what should make us cautious about the results — a limitation, an uncertainty, a sampling constraint, or a different explanation the evidence can't rule out.",
        "hint": "Think about who or what was NOT included, or another reason the results might have come out the way they did.",
        "example": "For example, in a different study someone might say: 'Only 20 people took part, so we can't be sure it generalizes.' Now consider a limitation specific to this paper.",
    },
    "warranted_interpretation": {
        "label": "Warranted interpretation",
        "criteria": [
            "states a conclusion the evidence supports",
            "distinguishes it from a stronger conclusion the evidence does not support",
        ],
        "sufficient_when": "the learner offers a conclusion justified by the evidence and notes where it would become overreach.",
        "not_this": "restating the finding as certain fact or overgeneralizing beyond the study.",
        "explain": "I'm asking what conclusion the evidence actually justifies — and, importantly, where a stronger-sounding conclusion would go beyond what the study can show.",
        "hint": "Think about what the results reasonably support, versus a bigger claim the authors would NOT be entitled to make.",
        "example": "For example, in a different study someone might say: 'The results support that reminders help adherence, but not that they cure the underlying illness.' Now try that distinction for this paper.",
    },
}


def stage_rubric(stage):
    if stage not in RUBRIC:
        raise ValueError("Unknown structured stage")
    return RUBRIC[stage]
