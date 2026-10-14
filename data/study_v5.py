"""Candidate V5 instrument. No historical instrument is changed."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
from data.crossover import BASELINE_ITEMS as OLD_BASELINE, PAPERS as OLD_PAPERS, CONSENT_PATH, CONSENT_SHA256, FINAL_SURVEY_TEXT
from data.study_v4 import MENTOR_STAGES, MENTOR_QUESTIONS, FINAL_SURVEY_ITEMS
from data.mentor_rubric import MENTOR_MAX_ATTEMPTS
ROOT=Path(__file__).resolve().parents[1]
# v8 adds adaptive help controls + verified source pointers + deterministic NO_ATTEMPT
# pre-check to the structured mentor (v7 already installed the free Self-Directed fix,
# so its manifest is immutable and the prompt change re-mints under a new release id).
# Items, papers, consent, and scales are unchanged. Earlier releases remain queryable.
RELEASE_ID='v8-crossover-2026-09-18'
INSTRUMENT_VERSION=RELEASE_ID+'-items-1'
PROMPT_VERSION=RELEASE_ID+'-adaptive-mentor-1'
# Amended September 7, 2026 on the researcher's explicit instruction: no scheduled cutoff.
# Recruitment now closes only by researcher action through V5_RECRUITMENT_OPEN. Set an ISO
# timestamp here to reinstate a fixed close. Not part of snapshot(), so the frozen instrument
# hash is unaffected; the cap of 60 production randomizations still applies.
ENROLLMENT_CLOSE=None
TARGET_PAIRS=34
ENROLLMENT_CAP=60
MODEL_ID='deepseek/deepseek-v4-flash-0731'
GENERATION={'model':MODEL_ID,'temperature':0.1,'top_p':0.1,'max_tokens':2048,'extra_body':{'reasoning':{'enabled':False,'exclude':True}}}
SEQUENCES={'S1':[('paper_a','self_directed'),('paper_b','structured')], 'S2':[('paper_a','structured'),('paper_b','self_directed')], 'S3':[('paper_b','self_directed'),('paper_a','structured')], 'S4':[('paper_b','structured'),('paper_a','self_directed')]}
STAGES=['baseline']+[f'{p}_{s}' for p in (1,2) for s in ('read','tutor','quiz','followup')]+['final']
BUDGETS={'baseline':180,'read':360,'tutor':360,'quiz':240,'followup':120,'final':60}
TRUST={k:deepcopy(FINAL_SURVEY_ITEMS[k]) for k in ('trust_item_1','trust_item_2','trust_item_3')}
PAPERS=deepcopy(OLD_PAPERS)
BASELINE_ITEMS=deepcopy(OLD_BASELINE)
for paper_id,items in [('baseline',BASELINE_ITEMS)]+[(k,v['mcqs']) for k,v in PAPERS.items()]:
    for item in items:
        item.update(instrument_version=INSTRUMENT_VERSION,paper_id=paper_id,learning_objective=item['question_category'],reviewer_status='pending',item_status='review')
def snapshot():
    return {'release_id':RELEASE_ID,'instrument_version':INSTRUMENT_VERSION,'baseline':BASELINE_ITEMS,'papers':PAPERS,'trust':TRUST,'final':deepcopy(FINAL_SURVEY_TEXT),'budgets':BUDGETS,'required_exchanges':5,'consent_sha256':CONSENT_SHA256}
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def frozen_manifest():
    path=ROOT/'data/v5_manifest.json'
    if not path.exists(): raise ValueError('V5 candidate is not frozen')
    m=json.loads(path.read_text())
    if m['instrument_hash']!=digest(snapshot()): raise ValueError('Frozen instrument differs from source; create a new release')
    if hashlib.sha256(CONSENT_PATH.read_bytes()).hexdigest()!=m['consent_sha256']: raise ValueError('Consent artifact changed')
    if hashlib.sha256((ROOT/'v5_tutor.py').read_bytes()).hexdigest()!=m['prompt_source_sha256']: raise ValueError('Frozen prompt implementation changed')
    if hashlib.sha256((ROOT/'data/mentor_rubric.py').read_bytes()).hexdigest()!=m.get('rubric_source_sha256'): raise ValueError('Frozen mentor rubric changed')
    if m['generation_settings']!=GENERATION: raise ValueError('Frozen generation settings changed')
    return m
