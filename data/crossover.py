"""Frozen crossover release. Historical V4 content remains in study_v4.py."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from data.study_v4 import *

RELEASE_ID = "v4-crossover-2026-09-06"
CONTENT_VERSION = RELEASE_ID + "-content-1"
INSTRUMENT_VERSION = RELEASE_ID + "-items-1"
PROMPT_VERSION = RELEASE_ID + "-summary-mentor-1"
CONSENT_PATH = Path(__file__).resolve().parents[1] / "data/consent/approved_crossover_consent.pdf"
CONSENT_SHA256 = hashlib.sha256(CONSENT_PATH.read_bytes()).hexdigest()
CONSENT_ARTIFACT_ID = "sha256:" + CONSENT_SHA256
TARGET_PAIRS = 34
ENROLLMENT_CAP = 60
ENROLLMENT_CLOSE = "2026-09-08T03:59:00+00:00"

def question(item_id, category, text, options, key, evidence, rationale, distractors):
    assert len(options) == 4 and len(set(options)) == 4 and 0 <= key < 4
    return dict(item_id=item_id, question_category=category, question_text=text,
                answer_options=options, correct_answer=options[key],
                option_ids=[f"{item_id}_o{i+1}" for i in range(4)],
                correct_option_id=f"{item_id}_o{key+1}", source_evidence=evidence,
                key_rationale=rationale, distractor_rationales=distractors)

PAPERS = deepcopy(PAPERS)
PAPERS['paper_a']['mcqs'] = [
 question('pa_central','central_finding',
 'A moderation team wants to apply the findings. Which recommendation best reflects the study?',
 ['Use the highest similarity score as the main release criterion.',
  'Keep human review alongside checks of generated references.',
  'Prefer extra reasoning steps over supplying relevant sources.',
  'Replace the human reference notes with model-generated ones.'],1,
 'Paper A summary: What inspection revealed; A cautious conclusion.',
 'Reference problems and limited evaluation support continued human review.',
 ['Similarity alone does not establish factual reliability.','Extra reasoning was not consistently beneficial.','Human notes supplied the comparison, not an obsolete resource.']),
 question('pa_method','methodological_reasoning',
 'What does comparing generated notes with helpful Community Notes primarily measure here?',
 ['Whether generated notes resemble the selected human references.',
  'Whether readers change their beliefs after seeing generated notes.',
  'Whether generated links remain accessible several months later.',
  'Whether the sampled tweets represent each language used online.'],0,
 'Paper A: Methods 2.3 and Table 1; summary Proof-of-concept comparison.',
 'The reported automatic metrics compare generated text with reference text.',
 ['Reader belief change was not measured.','Long-term link availability was not the comparison.','The English sample cannot establish language coverage.']),
 question('pa_evidence','evidence_conclusion',
 'Which comparison best supports the claim that supplying sources helped the open models?',
 ['GPT-4o-mini and Qwen had similar scores when sources were supplied.',
  'The full benchmark contained more examples than the evaluation subset.',
  'Four automatic metrics were used alongside inspection of model outputs.',
  'Their scores rose from few-shot prompts to prompts with web references.'],3,
 'Paper A Table 1; summary What the scores showed.',
 'Comparing prompting conditions within the open models addresses the source intervention.',
 ['A cross-model comparison does not isolate access to sources.','Dataset size is not evidence of improvement.','Using several measures does not establish their direction.']),
 question('pa_limit','limitation_uncertainty',
 'Suppose a generated note receives a high BERTScore. What still needs separate checking?',
 ['Whether its wording overlaps the selected human reference note.',
  'Whether it was included among the notes scored automatically.',
  'Whether its factual claims and cited sources are dependable.',
  'Whether its model used the same spelling as the reference note.'],2,
 'Paper A automated metrics and qualitative inspection of reference validity.',
 'Text similarity does not itself establish truth or reference validity.',
 ['Similarity is what the score already addresses.','Sample membership is not the unresolved validity issue.','Spelling agreement does not establish factual reliability.']),
 question('pa_overclaim','unsupported_inference',
 'A team reports that adding reasoning steps will improve its new moderation model. How should this paper inform that expectation?',
 ['Expect gains because supplying sources helped the open models.',
  'Test that model; the reasoning changes had mixed results here.',
  'Expect losses because one tested model declined on the metrics.',
  'Use the full benchmark size to predict the direction of change.'],1,
 'Paper A Table 1; summary What the scores showed and A cautious conclusion.',
 'Mixed, model-specific results do not establish a uniform effect for a new model.',
 ['Source provision is a different intervention.','One decline does not predict every model.','Benchmark size does not determine the treatment direction.']),
]
PAPERS['paper_b']['mcqs'] = [
 question('pb_central','central_finding',
 'Which design priority best follows from the blind artists study?',
 ['Use image-generation speed as the main measure of artistic agency.',
  'Use digital artists as proxies for artists working in tactile media.',
  'Provide descriptions that support artists in judging their own outputs.',
  'Provide a single assessment of AI art based on the majority reaction.'],2,
 'Paper B findings and discussion; summary What explainability should provide.',
 'Descriptions and explanations can support agency amid varied participant needs.',
 ['Speed was not established as an agency measure.','The study highlights varied media and perspectives.','A single reaction would erase meaningful differences.']),
 question('pb_method','methodological_reasoning',
 'What did the real-time image-generation activity add to the interviews?',
 ['It let artists respond to examples produced from their own requests.',
  'It isolated image quality from the researcher’s verbal descriptions.',
  'It compared independent use by experienced and first-time users.',
  'It measured how using AI changed the artists’ income over time.'],0,
 'Paper B Methodology; summary Participants and procedure.',
 'Participants supplied prompts and discussed resulting images with the researcher.',
 ['The researcher mediated the experience.','None had previously used Midjourney and use was mediated.','Income effects were not measured.']),
 question('pb_evidence','evidence_conclusion',
 'Which observation directly supports a concern about representing blind people’s experiences?',
 ['Artists described working with both digital and physical materials.',
  'A researcher described the generated images during the interviews.',
  'Participants expressed different views about AI as a creative partner.',
  'Generated images included incorrect Braille and missing guide-dog gear.'],3,
 'Paper B Table 2 and findings; summary Failures involving blindness.',
 'These outputs mismatch concrete features of the participants’ requests.',
 ['Artistic medium is not an output representation failure.','Mediation alone does not identify an inaccurate output.','Varied opinions do not establish these specific failures.']),
 question('pb_limit','limitation_uncertainty',
 'Why is a follow-up study of independent tool use needed?',
 ['The interviews did not include participants working in visual art.',
  'A sighted researcher entered prompts and described the images.',
  'The participants had extensive prior experience with Midjourney.',
  'The researchers compared several competing image generators.'],1,
 'Paper B Methodology; summary Participants and procedure.',
 'Researcher assistance means the study did not directly establish independent usability.',
 ['Participants were artists across visual and tactile media.','None had used Midjourney previously.','This was not a comparison of competing generators.']),
 question('pb_overclaim','unsupported_inference',
 'Which proposed statement would need evidence beyond these interviews?',
 ['Some artists saw potential for AI to contribute to creative work.',
  'The examples reveal unmet needs in representing blindness.',
  'Explanations of artistic choices mattered to interviewed artists.',
  'Using the tool independently improves blind artists’ productivity.'],3,
 'Paper B Methods and Discussion; summary A cautious conclusion.',
 'Independent use and productivity improvement were not tested.',
 ['Creative possibilities were discussed.','The output examples support this limited claim.','Participants requested such explanations.']),
]

BASELINE_ITEMS = [
 question('base_alternative_explanations','alternative_explanations',
 'Students choose whether to use an AI study tool. Users later score higher. Which information best helps assess whether the tool caused the difference?',
 ['How the two groups scored before choosing to use the tool.',
  'How often users recommended the tool to their classmates.',
  'How many different question topics the tool could explain.',
  'How quickly the tool displayed answers during practice.'],0,
 'General research reasoning: self-selection and baseline comparability.',
 'Pre-existing performance differences offer an alternative explanation.',
 ['Recommendation is not baseline comparability.','Coverage does not address self-selection.','Response speed does not address prior group differences.']),
 question('base_methodological_reasoning','methodological_reasoning',
 'Why randomly assign students to two forms of AI assistance?',
 ['To ensure both forms produce the same amount of learning.',
  'To make the volunteers representative of all university students.',
  'To reduce systematic differences in who receives each form.',
  'To ensure each student follows the assigned instructions.'],2,
 'General research reasoning: purpose of random assignment.',
 'Random assignment reduces systematic allocation differences in expectation.',
 ['Randomization does not guarantee equal outcomes.','Assignment is different from population sampling.','Assignment does not guarantee adherence.']),
 question('base_correlation_causation','correlation_causation',
 'A survey finds that frequent AI users have higher grades. What does this observation establish?',
 ['Using AI more often raises a student’s grades over time.',
  'AI-use frequency and grades are related in the surveyed group.',
  'Students receive higher grades before increasing their AI use.',
  'AI use explains the grade differences between departments.'],1,
 'General research reasoning: observational association.',
 'The observation establishes association without direction or causal attribution.',
 ['Causal direction was not established.','Temporal order was not established.','Department-level explanation was not tested.']),
 question('base_generalizability','generalizability',
 'An AI activity works well in one small university class. What is the most useful next step before recommending it across courses?',
 ['Use the same class’s satisfaction ratings as confirmation.',
  'Compare the class average with unrelated national grades.',
  'Recruit more students only from that instructor’s class.',
  'Test the activity with students in other course settings.'],3,
 'General research reasoning: external validity.',
 'Testing other settings directly examines whether the finding generalizes.',
 ['Satisfaction in the same setting does not test generalization.','Unrelated grades are not a comparable evaluation.','A larger same-setting sample does not address setting differences.']),
 question('base_evidence_conclusion_alignment','evidence_conclusion_alignment',
 'An AI tutor is claimed to improve evidence evaluation, but its test asks students to recall definitions. Which revision best tests the claim?',
 ['Add items asking which conclusion follows from presented results.',
  'Add more definitions covering a wider range of research topics.',
  'Ask students to rate how clearly the tutor explained the definitions.',
  'Give students more time to recall each definition accurately.'],0,
 'General research reasoning: alignment of outcome and claimed skill.',
 'Interpreting results measures evidence evaluation more directly than recall.',
 ['More recall items do not change the construct.','Clarity ratings do not measure the claimed skill.','Extra time does not correct construct mismatch.']),
]
PRETEST_ITEMS = BASELINE_ITEMS
for paper in PAPERS.values():
    paper['version'] = CONTENT_VERSION

SCOPE_NOTE = ('You have access only to the supplied study summary, not the full PDF, figures or tables. '
              'If a question needs details absent from this summary, say that you cannot verify them and '
              'invite the learner to inspect the source. Never pretend to have read the full paper. ')
GENERIC_TUTOR_PROMPT = SCOPE_NOTE + GENERIC_TUTOR_PROMPT
STRUCTURED_TUTOR_PROMPT = SCOPE_NOTE + STRUCTURED_TUTOR_PROMPT
STRUCTURED_OPENING = ('Let’s discuss this study summary. Give a brief, one-sentence response at each step; '
                      'it is fine to say what you are unsure about. I can discuss the summary, but cannot inspect the full PDF.')
MENTOR_QUESTIONS = {key: value + ' One sentence is enough.' for key, value in MENTOR_QUESTIONS.items()}
FINAL_SURVEY_ITEMS = deepcopy(FINAL_SURVEY_ITEMS)
for key, text in {
    'trust_item_1': 'Considering both papers, I felt confident in the information provided by the AI assistants.',
    'trust_item_2': 'Considering both papers, the AI assistants seemed reliable when discussing the research.',
    'trust_item_3': 'Overall, I trusted the AI assistants across both papers.',
    'tutor_helpfulness': 'Overall, how helpful were the AI assistants across both papers? (1 = Not at all helpful; 7 = Extremely helpful)',
}.items():
    FINAL_SURVEY_ITEMS[key]['question'] = text
FINAL_SURVEY_TEXT = deepcopy(FINAL_SURVEY_TEXT)
FINAL_SURVEY_TEXT['ai_discrepancy_text']['question'] = 'Describe what seemed unsupported, if you wish. (optional)'
FINAL_SURVEY_TEXT['ai_use_strategy_text']['question'] = 'How did you use the assistants? (optional)'
FINAL_SURVEY_TEXT['prohibited_tool_report']['question'] = 'Did you consult a paper, saved chat, AI tool, or other outside resource during either independent quiz?'
FINAL_SURVEY_TEXT['assistant_preference'] = {'question':'Which assistant interaction did you prefer?',
    'options':['First assistant','Second assistant','Neither','No preference']}
POST_PAPER_SURVEY = deepcopy(POST_PAPER_SURVEY)
POST_PAPER_SURVEY['assistant_helpfulness'] = {'question':'How helpful was this assistant for understanding the paper?', 'options':list(range(1,8))}

def assessment_items(paper_id):
    return PAPERS[paper_id]['mcqs']

def tutor_paper_context(paper_id):
    paper = PAPERS[paper_id]
    sections = '\n\n'.join(f'{heading}\n{text}' for heading,text in paper['display_content'])
    return f"Study summary only (full PDF is not available to the assistant).\n{paper['citation']}\n\n{sections}"

def instrument_snapshot():
    return {'release_id':RELEASE_ID, 'content_version':CONTENT_VERSION,
            'instrument_version':INSTRUMENT_VERSION,'prompt_version':PROMPT_VERSION,
            'papers':PAPERS,'baseline_items':BASELINE_ITEMS,
            'mentor_questions':MENTOR_QUESTIONS,'structured_opening':STRUCTURED_OPENING,
            'generic_prompt':GENERIC_TUTOR_PROMPT,'structured_prompt':STRUCTURED_TUTOR_PROMPT,
            'final_survey_items':FINAL_SURVEY_ITEMS,'final_survey_text':FINAL_SURVEY_TEXT,
            'post_paper_survey':POST_PAPER_SURVEY,'baseline_instructions':BASELINE_INSTRUCTIONS}

def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_release_artifacts():
    """A release ID never silently acquires a different instrument or source file."""
    manifest = json.loads((Path(__file__).parent / "crossover_manifest.json").read_text())
    if manifest['instrument_sha256'] != snapshot_hash(instrument_snapshot()) or manifest['consent_sha256'] != CONSENT_SHA256:
        raise ValueError("Frozen release content differs from its manifest; enrollment is unavailable.")
    root = Path(__file__).resolve().parents[1]
    for paper in PAPERS.values():
        if hashlib.sha256((root / paper['local_pdf_path']).read_bytes()).hexdigest() != paper['pdf_sha256']:
            raise ValueError("A frozen source PDF differs from the approved release manifest.")
    return manifest
