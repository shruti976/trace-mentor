"""Central, replaceable content and design configuration for the EAAI V4 study.

The display passages are short study adaptations rather than copies of the
research-team-supplied PDFs. They MUST receive content-expert, permission, and
IRB review before real V4 recruitment is opened.
"""

from __future__ import annotations


STUDY_VERSION = "v4"
CONTENT_VERSION = "v4-baseline-assessment-2026-09-03"
PROMPT_VERSION = "research-mentor-v4-draft-1"
TUTOR_CONDITIONS = ("generic", "structured")
PAPER_IDS = ("paper_a", "paper_b")


def _item(item_id: str, category: str, question: str, options: list[str], answer: str) -> dict:
    if len(options) != 4 or options.count(answer) != 1:
        raise ValueError(f"{item_id} must have four choices and exactly one keyed answer")
    return {
        "item_id": item_id,
        "question_category": category,
        "question_text": question,
        "answer_options": options,
        "correct_answer": answer,
    }


PAPERS = {
    "paper_a": {
        "paper_id": "paper_a",
        "title": "On the Limitations of LLM-Synthesized Social Media Misinformation Moderation",
        "short_title": "LLMs and misinformation moderation",
        "authors": "Sahajpreet Singh, Jiaying Wu, Svetlana Churina, and Kokil Jaidka",
        "venue": "I Can't Believe It's Not Better Workshop at ICLR",
        "year": 2025,
        "citation": "Singh, S., Wu, J., Churina, S., & Jaidka, K. (2025). On the Limitations of LLM-Synthesized Social Media Misinformation Moderation. I Can't Believe It's Not Better Workshop at ICLR 2025.",
        "source_url": "https://iclr.cc/virtual/2025/33595",
        "optional_pdf_url": "https://openreview.net/pdf?id=ilz2ghLgzt",
        "local_pdf_path": "data/papers/v4/limitations_llm_misinformation_moderation.pdf",
        "pdf_sha256": "bd12e581ff123641e731949556bf625ba4cd3611bd1147d150c1af05393a3d18",
        "rendered_page_paths": [f"data/papers/v4/rendered/paper_a/page-{page}.jpg" for page in range(1, 8)],
        "figure_or_table_assets": [],
        "version": CONTENT_VERSION,
        "permission_status": "Research-team supplied PDF and normalized study summary; reproduction permission and content review required before recruitment",
        "display_content": [
            ("The moderation problem", "Community-based misinformation programs can attach explanatory notes to misleading social-media posts, but writing useful notes at scale is difficult. The authors ask whether large language models can generate moderation notes that are as specific, useful, truthful, and well supported as notes written and rated by people."),
            ("MODBENCH", "The paper introduces MODBENCH, a benchmark assembled from public Community Notes data. After processing English tweet-note pairs from 2018 through 2023, the dataset contains 133,436 entries involving tweets marked as misinformed or potentially misleading and notes that contributors rated helpful. Human-written notes serve as the reference responses."),
            ("Proof-of-concept comparison", "The authors evaluate a random sample of 1,000 tweet-note pairs with three models: Llama-3.1-8B-Instruct, Qwen-2.5-7B-Instruct-1M, and GPT-4o-mini. They compare few-shot prompting, access to web references, and chain-of-thought prompting with web references. Outputs are scored with BLEU, METEOR, ROUGE-L, and BERTScore, then inspected for qualities such as specificity, usefulness, truthfulness, and valid references."),
            ("What the scores showed", "Adding web references produced the clearest improvement over few-shot prompting for the two open models. Qwen with web references reached a BERTScore of 0.869, while GPT-4o-mini reached 0.871. Adding chain-of-thought did not consistently improve results: for example, Qwen's scores were lower with chain-of-thought plus web references than with web references alone."),
            ("What inspection revealed", "The authors found that Qwen sometimes produced malformed, incomplete, or fabricated references and structural artifacts. In the outputs they inspected, GPT-4o-mini was more coherent and did not fabricate links, although it still remained only marginally ahead on the automated measures. The models generally cross-checked sources when references were supplied."),
            ("A cautious conclusion", "In this proof of concept, model-generated notes still had important shortcomings relative to human-authored notes. The results suggest that trustworthy sources and human expertise remain important in misinformation moderation. The study uses only a 1,000-item subset, automated similarity metrics, and qualitative inspection, so it does not establish that every model or every automated moderation design will fail."),
        ],
        "mcqs": [
            _item("pa_central", "central_finding", "What is the paper's main conclusion?", ["Current LLMs fully replace human judgment in misinformation moderation", "Current LLM-generated notes still fall short of human-authored notes, and dependable sources and human expertise remain important", "Few-shot prompting makes all three models equally accurate", "Automated moderation should never use web sources"], "Current LLM-generated notes still fall short of human-authored notes, and dependable sources and human expertise remain important"),
            _item("pa_method", "methodological_reasoning", "Why did the authors compare generated notes with helpful human-written Community Notes?", ["To provide a reference for judging how closely model outputs matched useful moderation notes", "To determine which social-media users had the most followers", "To train all three language models from scratch", "To prove that every human-written note is factually correct"], "To provide a reference for judging how closely model outputs matched useful moderation notes"),
            _item("pa_evidence", "evidence_conclusion", "Which result most directly supports the claim that access to sources helped the models?", ["The dataset included posts from several years", "Web-reference prompting substantially improved the open models' similarity scores over few-shot prompting", "GPT-4o-mini has a longer name than Qwen", "The authors used four automatic metrics"], "Web-reference prompting substantially improved the open models' similarity scores over few-shot prompting"),
            _item("pa_limit", "limitation_uncertainty", "Which feature most limits a broad claim about all LLM-based moderation systems?", ["The proof of concept evaluated 1,000 sampled pairs with a small set of models and measures", "The paper gives the models descriptive names", "The dataset contains English text", "The authors report both numerical and qualitative observations"], "The proof of concept evaluated 1,000 sampled pairs with a small set of models and measures"),
            _item("pa_overclaim", "unsupported_inference", "Which statement goes beyond the evidence in this paper?", ["Providing web references can improve generated moderation notes", "Generated references should be checked for validity", "Chain-of-thought prompting always improves every model's moderation output", "Human-authored notes remain a useful comparison point"], "Chain-of-thought prompting always improves every model's moderation output"),
        ],
    },
    "paper_b": {
        "paper_id": "paper_b",
        "title": "Exploring Use and Perceptions of Generative AI Art Tools by Blind Artists",
        "short_title": "Generative AI art tools and blind artists",
        "authors": "Gayatri Raman and Erin Brady",
        "venue": "Explainable AI for the Arts Workshop",
        "year": 2024,
        "citation": "Raman, G., & Brady, E. (2024). Exploring Use and Perceptions of Generative AI Art Tools by Blind Artists. Proceedings of the Explainable AI for the Arts Workshop 2024, 4 pages.",
        "source_url": "https://arxiv.org/abs/2409.08226",
        "optional_pdf_url": "https://xaixarts.github.io/accepted-2024/Raman-XAIxArts-2024-paper.pdf",
        "local_pdf_path": "data/papers/v4/blind_artists_generative_ai.pdf",
        "pdf_sha256": "73afe202b2167be33c500cead6a9f067e154c603da819dc25714adec89b5c0f6",
        "rendered_page_paths": [f"data/papers/v4/rendered/paper_b/page-{page}.jpg" for page in range(1, 5)],
        "figure_or_table_assets": [],
        "version": CONTENT_VERSION,
        "permission_status": "Research-team supplied PDF and normalized study summary; reproduction permission and content review required before recruitment",
        "display_content": [
            ("Why this study was needed", "Research on AI-generated art has mostly focused on sighted artists and consumers. The authors investigate how blind artists understand and respond to generative-AI art tools, including whether these tools support creativity and what kinds of accessibility and explanation are needed."),
            ("Participants and procedure", "The researchers recruited six blind artists through public art-sharing accounts and professional websites. In guided, open-ended interviews, participants discussed their art and took part in real-time Midjourney interactions. Participants supplied prompts, while a sighted researcher entered them and verbally described the generated images. None of the six had previously used Midjourney."),
            ("Mixed views of AI art", "Participants did not share one reaction. Some digital artists worried that people would assume their work was AI-generated or value it less. Others felt less threatened because their work was distinctive or tactile. Participants also imagined AI as a collaborator: it might provide inspiration, help evaluate or clean up work, or become another artistic medium."),
            ("Failures involving blindness", "Some outputs did not represent the artists' requests accurately. Examples included incorrect Braille, a mouse shown without tactilely reading Braille, and a regular dog instead of a guide dog with a harness. These failures raised concerns about stereotypes, exclusion from training data, and whether a system could reflect blind people's lived experience."),
            ("What explainability should provide", "Participants wanted more than a basic image description. They wanted objective information about how their prompts related to the generated image, along with explanations of subjective artistic choices. Detailed scene descriptions and dialogue with the system could give blind artists more agency when evaluating and revising an output."),
            ("A cautious conclusion", "The interviews identify possible creative benefits alongside unmet accessibility and explainability needs. The findings are preliminary: they come from six participants, and the Midjourney sessions were mediated by a sighted researcher. The study therefore offers design insights and questions for future work, not proof that generative-AI art tools help or harm all blind artists."),
        ],
        "mcqs": [
            _item("pb_central", "central_finding", "What is the paper's central contribution?", ["It proves that blind artists reject all AI-generated art", "It identifies blind artists' varied views of generative art and their unmet needs for accessibility and meaningful explanations", "It compares the sales of human and AI artwork", "It introduces an image generator that reads Braille perfectly"], "It identifies blind artists' varied views of generative art and their unmet needs for accessibility and meaningful explanations"),
            _item("pb_method", "methodological_reasoning", "Why did the researchers include real-time Midjourney interactions in the interviews?", ["To let participants react to generated images based on prompts they provided", "To measure how quickly participants could type", "To train Midjourney on the participants' artwork", "To remove the need for verbal descriptions"], "To let participants react to generated images based on prompts they provided"),
            _item("pb_evidence", "evidence_conclusion", "Which observation most directly supports the concern that generated images can misrepresent blindness?", ["Some participants made tactile artwork", "Outputs included incorrect Braille and replaced a requested guide dog with a regular dog", "The researchers used guided, open-ended interviews", "The artists used several different media"], "Outputs included incorrect Braille and replaced a requested guide dog with a regular dog"),
            _item("pb_limit", "limitation_uncertainty", "What is the most important limitation when interpreting these findings?", ["Only six artists participated, and a sighted researcher mediated the Midjourney interactions", "Participants were allowed to choose their own prompts", "The paper discusses more than one type of artwork", "The researchers asked open-ended questions"], "Only six artists participated, and a sighted researcher mediated the Midjourney interactions"),
            _item("pb_overclaim", "unsupported_inference", "Which claim is not supported by this study?", ["Blind artists can have different reactions to AI-generated art", "Detailed descriptions may increase artists' agency over generated images", "Generative-AI art tools improve creative independence for every blind artist", "Inaccessible or stereotyped outputs deserve further study"], "Generative-AI art tools improve creative independence for every blind artist"),
        ],
    },
}


# V4 Baseline Assessment. Five related but distinct research-evaluation skills, measured once
# before either tutor condition. It is a participant-level covariate for the post-paper models --
# NOT a validated research-literacy scale, an ability or intelligence measure, or the first half
# of a pre/post learning-gain comparison. Never difference it against the paper quizzes: the two
# measure related but non-identical constructs, and the post-paper MCQs remain the primary outcome.
# Planned use: post_reading_correct ~ condition + baseline_score + paper + period + covariates.
BASELINE_ITEMS = [
    _item(
        "base_alternative_explanations", "alternative_explanations",
        "A study reports that students who used an AI learning tool scored higher than students who did not. What is the most important question to consider before concluding that the tool improved performance?",
        [
            "Whether the tool has a memorable name",
            "Whether the groups were comparable and other explanations for the difference were addressed",
            "Whether the scores were reported first in a table or a figure",
            "Whether every student said that they liked the tool",
        ],
        "Whether the groups were comparable and other explanations for the difference were addressed",
    ),
    _item(
        "base_methodological_reasoning", "methodological_reasoning",
        "Researchers want to determine whether providing an AI-generated explanation improves students' understanding. Why would randomly assigning students to receive or not receive the explanation strengthen the study?",
        [
            "It guarantees that every student will learn the material",
            "It helps reduce systematic pre-existing differences between the groups",
            "It guarantees that the sample represents every type of student",
            "It removes the need to measure learning outcomes",
        ],
        "It helps reduce systematic pre-existing differences between the groups",
    ),
    _item(
        "base_correlation_causation", "correlation_causation",
        "Students who use an AI assistant more frequently also tend to earn higher grades. Which conclusion is best supported by this observation alone?",
        [
            "Using the AI assistant causes students to earn higher grades",
            "Higher grades cause students to use the AI assistant more often",
            "AI-assistant use and grades are associated, but the direction and cause are not established",
            "The relationship proves that students who do not use AI will receive lower grades",
        ],
        "AI-assistant use and grades are associated, but the direction and cause are not established",
    ),
    _item(
        "base_generalizability", "generalizability",
        "A study with a small group of students in one university course finds that an intervention improves performance. Which conclusion is most appropriate?",
        [
            "The intervention will improve performance in every university course",
            "The result provides evidence for that setting, but it should be tested in other populations and contexts",
            "The intervention has been proven to work universally",
            "Because the sample is small, the study provides no useful information",
        ],
        "The result provides evidence for that setting, but it should be tested in other populations and contexts",
    ),
    _item(
        "base_evidence_conclusion_alignment", "evidence_conclusion_alignment",
        "A paper claims that an AI assistant improves students' ability to evaluate research evidence. Students using the assistant score higher on a quiz containing only factual recall questions. What is the main concern with this conclusion?",
        [
            "The researchers should have used more technical terminology in the quiz",
            "The measured outcome does not directly test the evidence-evaluation ability claimed by the authors",
            "Factual recall questions should never be used in research studies",
            "The AI assistant should have produced responses more quickly",
        ],
        "The measured outcome does not directly test the evidence-evaluation ability claimed by the authors",
    ),
]

# Backward-compatible alias. The stage key, the stored `stage` value, and `pretest_score` keep
# their names so existing analysis code and V3 rows are untouched; participants see
# "Baseline Assessment" throughout the interface.
PRETEST_ITEMS = BASELINE_ITEMS

BASELINE_INSTRUCTIONS = (
    "Answer the following five questions based on your current understanding. These questions "
    "assess general research reasoning and do not require knowledge of the papers you will read "
    "later. Correct answers will not be shown during the study."
)


SEQUENCES = {
    "sequence_1": {"condition": "generic", "paper_order": ("paper_a", "paper_b")},
    "sequence_2": {"condition": "generic", "paper_order": ("paper_b", "paper_a")},
    "sequence_3": {"condition": "structured", "paper_order": ("paper_a", "paper_b")},
    "sequence_4": {"condition": "structured", "paper_order": ("paper_b", "paper_a")},
}

# Within-subjects design: every participant reads one paper with the structured mentor and the
# other with the generic assistant. Fully crossed across four cells -- paper_a carries the
# structured condition in half of them, appears first in half, and structured occupies period 1
# in half. Paper and condition therefore vary independently; neither is confounded with the other.
WITHIN_SEQUENCES = {
    "within_1": {"periods": ({"paper_id": "paper_a", "condition": "structured"},
                             {"paper_id": "paper_b", "condition": "generic"})},
    "within_2": {"periods": ({"paper_id": "paper_b", "condition": "generic"},
                             {"paper_id": "paper_a", "condition": "structured"})},
    "within_3": {"periods": ({"paper_id": "paper_a", "condition": "generic"},
                             {"paper_id": "paper_b", "condition": "structured"})},
    "within_4": {"periods": ({"paper_id": "paper_b", "condition": "structured"},
                             {"paper_id": "paper_a", "condition": "generic"})},
}

DESIGN_MODELS = ("between_subjects", "within_subjects")


def sequence_table(design_model: str) -> dict:
    """Return the allocation table for a design model."""
    if design_model == "within_subjects":
        return WITHIN_SEQUENCES
    if design_model == "between_subjects":
        return SEQUENCES
    raise ValueError(f"Unknown V4 design model: {design_model!r}. Expected one of {DESIGN_MODELS}.")


def sequence_periods(design_model: str, sequence_id: str) -> tuple:
    """Normalise either design to a per-period ({paper_id, condition}, ...) tuple."""
    table = sequence_table(design_model)
    entry = table[sequence_id]
    if "periods" in entry:
        return tuple(dict(period) for period in entry["periods"])
    return tuple({"paper_id": paper_id, "condition": entry["condition"]} for paper_id in entry["paper_order"])


MENTOR_STAGES = (
    "central_finding",
    "methodology",
    "evidence",
    "critical_perspective",
    "warranted_interpretation",
)

MENTOR_QUESTIONS = {
    "central_finding": "In your own words, what do you think is the central finding or main contribution of this paper?",
    "methodology": "What important methodological choice did the authors make, and why do you think that choice was useful for answering their research question?",
    "evidence": "Which result, observation, figure, table, quotation, or data point provides strong support for the paper's main conclusion?",
    "critical_perspective": "What limitation, uncertainty, or alternative explanation should we consider when interpreting the results?",
    "warranted_interpretation": "Given the evidence and limitations, what conclusion do you think is justified by this study?",
}

STRUCTURED_OPENING = (
    "Let's work through this paper together as we might in a research discussion. "
    "I'll guide you through several questions about the authors' reasoning and evidence. "
    "Use the paper when you need it, and explain what you think in your own words."
)

GENERIC_TUTOR_PROMPT = (
    "You are an AI research assistant helping a participant understand the provided research paper. "
    "Respond naturally to the participant's questions and ground answers only in the paper supplied by the application. "
    "Explain terminology, methods, findings, figures, results, or limitations when asked, but do not force a predefined reading or evaluation strategy. "
    "Do not require the participant to identify claims, evidence, methodology, limitations, or conclusions before receiving help. "
    "Assessment questions and answer keys are not available to you; do not predict, reveal, or answer them. "
    "If the paper does not support something, say so rather than inventing information."
)

STRUCTURED_TUTOR_PROMPT = (
    "You are an experienced research mentor helping a student learn how to critically read an AI research paper. "
    "Your goal is to guide the student's own reasoning, not to review the paper for them. The application controls a five-stage sequence: "
    "central finding, methodological reasoning, supporting evidence, limitations or alternatives, and warranted interpretation. "
    "At the current stage, respond to what the participant says with concise feedback, identify important omissions, and encourage refinement when useful. "
    "Do not replace their answer with a complete polished review. End by asking the exact next-stage question supplied by the application, unless the current stage is the final one. "
    "Encourage returning to the paper when evidence is needed. Base every factual claim only on the supplied paper and never fabricate results, figures, sample sizes, quotes, or conclusions. "
    "Assessment questions and answer keys are not available to you. Do not mention conditions, treatment, or group labels. Use a supportive research-mentor tone."
)


FINAL_SURVEY_ITEMS = {
    "trust_item_1": {"question": "I felt confident in the information provided by the AI assistant.", "scale": list(range(1, 8)), "required": True},
    "trust_item_2": {"question": "The AI assistant seemed reliable when discussing the research papers.", "scale": list(range(1, 8)), "required": True},
    "trust_item_3": {"question": "Overall, I trusted the AI assistant.", "scale": list(range(1, 8)), "required": True},
    "tutor_helpfulness": {"question": "Overall, how helpful was the AI assistant in understanding the research papers?", "scale": list(range(1, 8)), "required": True},
}

POST_PAPER_SURVEY = {
    "mental_effort": {
        "question": "How much mental effort did you invest in understanding this paper?",
        "options": list(range(1, 10)),
    },
    "predicted_score": {
        "question": "How many of the five questions do you think you answered correctly?",
        "options": list(range(0, 6)),
    },
    "verification_self_report": {
        "question": "While using the AI assistant, how often did you return to the research paper to verify information provided by the AI?",
        "options": list(range(1, 6)),
    },
}

FINAL_SURVEY_TEXT = {
    "noticed_ai_discrepancy": {
        "question": "Did you notice any information provided by the AI assistant that seemed inconsistent with or unsupported by the research paper?",
        "options": ["Yes", "No", "Unsure"],
    },
    "ai_discrepancy_text": {"question": "Briefly describe what you noticed. (required)"},
    "ai_use_strategy_text": {"question": "Briefly describe how you typically used the AI assistant while reading the research papers. (required)"},
    "prohibited_tool_report": {
        "question": "Did you use a prohibited external tool during an independent question section?",
        "options": ["No", "Yes"],
    },
    "material_interruption": {
        "question": "Was the study materially interrupted?",
        "options": ["No", "Yes"],
    },
    "optional_comment": {"question": "Optional comment"},
}


def assessment_items(paper_id: str) -> list[dict]:
    return PAPERS[paper_id]["mcqs"]


def tutor_paper_context(paper_id: str) -> str:
    """Return only participant-visible paper content; assessment data never enters tutor context."""
    paper = PAPERS[paper_id]
    sections = "\n\n".join(f"{heading}\n{text}" for heading, text in paper["display_content"])
    return f"Paper ID: {paper_id}\nTitle: {paper['title']}\nCitation: {paper['citation']}\n\n{sections}"
