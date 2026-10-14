"""Verified, paper-specific source-location maps for the "Where should I look?"
scaffold. Every ref below was taken from the actual paper text (data/papers/v5/
*.txt) — no headings, tables, or figures are invented. The tutor may ONLY point a
participant to locations listed here for the CURRENTLY ASSIGNED paper_id; if a
stage has no verified pointer, the caller falls back to a neutral concept cue.

`token` is a distinctive substring used to verify (in tests) that the referenced
location really exists in that paper's text, robust to the heading letter-spacing
produced by PDF extraction (comparison strips whitespace and lowercases).

Opening the paper remains a SEPARATE participant action (the "View research paper"
control); these pointers are location cues only and never open the paper.
"""

SOURCE_MAPS = {
    "paper_a": {
        "title": "On the Limitations of LLM-Synthesized Social Media Misinformation Moderation",
        "stage_sources": {
            "central_finding": [
                {"ref": "Section 1 (Introduction)", "token": "Introduction", "desc": "where the authors set up the problem and state their contribution"},
                {"ref": "Section 4 (Conclusion)", "token": "Conclusion", "desc": "where they summarise what the study found"},
            ],
            "methodology": [
                {"ref": "Section 2 (Materials & Methods)", "token": "Materials & Methods", "desc": "how the benchmark and the generated notes were produced"},
                {"ref": "Section 2.1 (MODBench Data Curation)", "token": "MODBench Data Curation", "desc": "how the dataset was assembled"},
                {"ref": "Section 2.3 (Experimental Details)", "token": "Experimental Details", "desc": "the experimental setup and models compared"},
            ],
            "evidence": [
                {"ref": "Section 3.1 (Quantitative Evaluation)", "token": "Quantitative Evaluation", "desc": "the automated-metric results"},
                {"ref": "Table 1", "token": "Table 1", "desc": "results on automated metrics (BLEU, METEOR, ROUGE-L, BERTScore)"},
                {"ref": "Section 3.2 (Qualitative Inspection)", "token": "Qualitative Inspection", "desc": "hand-inspected examples of the generated notes"},
            ],
            "critical_perspective": [
                {"ref": "Section 3.2 (Qualitative Inspection)", "token": "Qualitative Inspection", "desc": "where weaknesses in the generated notes are discussed"},
                {"ref": "Section 3.3 (Implication for Future CN Research)", "token": "Implication for Future", "desc": "open problems and cautions the authors raise"},
                {"ref": "Section 4 (Conclusion)", "token": "Conclusion", "desc": "limitations noted at the end"},
            ],
            "warranted_interpretation": [
                {"ref": "Section 3.3 (Implication for Future CN Research)", "token": "Implication for Future", "desc": "what the authors argue follows from the results"},
                {"ref": "Section 4 (Conclusion)", "token": "Conclusion", "desc": "their overall conclusion"},
            ],
        },
    },
    "paper_b": {
        "title": "Exploring Use and Perceptions of Generative AI Art Tools by Blind Artists",
        "stage_sources": {
            "central_finding": [
                {"ref": "Section 1 (Introduction and Related Work)", "token": "Introduction and Related Work", "desc": "where the authors motivate the study and state its aim"},
                {"ref": "Section 4 (Discussion and Next Steps)", "token": "Discussion and Next Steps", "desc": "where they summarise what they learned"},
            ],
            "methodology": [
                {"ref": "Section 2 (Methods and Demographics)", "token": "Methods and Demographics", "desc": "how participants were recruited and what they were asked to do"},
                {"ref": "Table 1 (Participant Demographics)", "token": "Participant Demographics", "desc": "who the participants were"},
            ],
            "evidence": [
                {"ref": "Section 3 (Findings)", "token": "Findings", "desc": "the study's findings"},
                {"ref": "Section 3.1 (Comparison with AI art)", "token": "Comparison with AI art", "desc": "what participants said comparing their work with AI art"},
                {"ref": "Table 2", "token": "Table 2", "desc": "prompts and images from the image-generation exercise"},
            ],
            "critical_perspective": [
                {"ref": "Section 3.3 (Explainability, 'Visibility' and Blindness)", "token": "Explainability", "desc": "concerns participants raised about stereotypes and transparency"},
                {"ref": "Section 4 (Discussion and Next Steps)", "token": "Discussion and Next Steps", "desc": "limitations and open questions"},
            ],
            "warranted_interpretation": [
                {"ref": "Section 4 (Discussion and Next Steps)", "token": "Discussion and Next Steps", "desc": "the conclusions the authors draw"},
            ],
        },
    },
}

# Neutral concept fallback per stage when no verified pointer exists (never invents a heading).
STAGE_CONCEPT = {
    "central_finding": "where the authors state what they set out to study and what they concluded",
    "methodology": "where the authors describe who or what they studied and how they collected evidence",
    "evidence": "where the authors report their specific results",
    "critical_perspective": "where the authors discuss limitations or open questions",
    "warranted_interpretation": "where the authors state what their results do and do not support",
}


def pointers(paper_id, stage):
    """Verified source pointers for the assigned paper + stage (possibly empty)."""
    return SOURCE_MAPS.get(paper_id, {}).get("stage_sources", {}).get(stage, [])


def fallback(stage):
    return STAGE_CONCEPT.get(stage, "the relevant part of the paper")
