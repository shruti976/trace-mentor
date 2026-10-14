"""Adaptive structured mentor. Full-paper requests built without loading any
assessment or survey objects. A single provider call returns a structured JSON
judgement of the learner's OWN attempt plus the participant-facing reply, so the
mentor never fabricates learner content and never reveals answers."""
import hashlib,json,re
from pathlib import Path
import v5_store as store
from data import study_v5 as spec
from data import mentor_rubric
from data import paper_source_maps

# Shared grounding/safety rules. Apply to BOTH conditions (paper-grounding + no
# answer leakage). Condition-specific behaviour lives in the protocols below.
RULES=('You are an AI research assistant grounded only in the assigned paper below. '
       'Answer using the paper; distinguish supported, partially supported, unsupported, and unclear. '
       'Do not invent results, sample sizes, methods, tables, quotations, or citations, and do not claim the paper states something it does not. '
       'You do not have the assessment questions or answers; never reveal, infer, or reference them. '
       'Be supportive and concise, and do not mention experimental labels, conditions, or groups. ')

# Self-Directed (condition A): a free assistant. Answers whatever the learner asks,
# directly — no attempt gate, no scaffolding sequence.
SELF_DIRECTED=("Answer the learner's question directly and helpfully using the assigned paper. "
       'If they ask for a summary, provide one; if they ask about the methods, findings, limitations, or terminology, explain it. '
       'Do not impose a sequence of topics, and do not ask the learner to attempt an answer before you help.')

JSON_CONTRACT=('Respond with a SINGLE JSON object and nothing else, using exactly these keys: '
       '{"classification": one of ["NO_ATTEMPT","OFF_TOPIC","CLARIFICATION_REQUEST","PARTIAL_ATTEMPT","SUBSTANTIVE_ATTEMPT","MISCONCEPTION"], '
       '"present_concepts": [short strings the learner actually stated], '
       '"missing_concepts": [short strings still needed], '
       '"misconception": "" or a brief description of an unsupported claim the learner made, '
       '"sufficient": true or false, '
       '"reply": the message shown to the learner}. '
       'If classification is NO_ATTEMPT, OFF_TOPIC, or CLARIFICATION_REQUEST, "sufficient" must be false and "reply" must ask the learner for their own brief attempt without giving the answer. '
       'Acknowledge only what appears in the learner message.')

def structured_protocol(stage,attempt_number):
    r=mentor_rubric.stage_rubric(stage)
    return ('You are guiding a five-stage reasoning discussion; the application controls the sequence and supplies the next stage, so do NOT ask the next-stage question. '
            'Never say or imply the learner stated something they did not write, and never fabricate their reasoning; acknowledge only what is in their message. '
            'If the learner gives no real attempt — only naming a topic or section (for example "summary", "methods", "table 1") or saying "idk"/"help"/"." — classify NO_ATTEMPT, ask them to try in their own words, and do NOT supply or hint the answer. '
            f'Current stage: {r["label"]}. A sufficient attempt: {r["sufficient_when"]} It should address: {"; ".join(r["criteria"])}. '
            f'Reject weak patterns such as: {r["not_this"]} '
            f'This is attempt {attempt_number} of {mentor_rubric.MENTOR_MAX_ATTEMPTS}. '
            'If the attempt is insufficient and attempts remain, give ONE targeted hint or ask ONE focused question grounded in the paper; do not reveal the answer. '
            'If this is the final permitted attempt, give brief instructional guidance so the learner can move on. Ask at most one question at a time. '
            'Set "sufficient" true only when the learner has, in their own words, met the criteria above.')

def source(paper_id,expected_hash=None):
    manifest=json.loads((spec.ROOT/'data/papers/v5/provenance.json').read_text())
    p=manifest[paper_id]; content=(spec.ROOT/p['text_path']).read_text()
    if hashlib.sha256(content.encode()).hexdigest()!=p['full_text_hash'] or (expected_hash and p['full_text_hash']!=expected_hash): raise ValueError('Canonical paper text hash mismatch')
    if hashlib.sha256((spec.ROOT/p['source_pdf']).read_bytes()).hexdigest()!=p['pdf_sha256']: raise ValueError('Displayed PDF hash mismatch')
    return p,content

def construct(a,history,current_text,structured_stage=None,attempt_number=1):
    """history is a list of (learner_text, mentor_reply) pairs already shown this period,
    including earlier attempts of the current stage. No assessment objects are ever loaded."""
    p,text=source(a['paper_id'],a['paper_text_hash'])
    if a['condition']=='structured':
        if structured_stage not in mentor_rubric.STAGES: raise ValueError('Invalid structured stage')
        system=RULES+structured_protocol(structured_stage,attempt_number)+' '+JSON_CONTRACT
    else:
        system=RULES+SELF_DIRECTED
    messages=[{'role':'system','content':system},
              {'role':'system','content':f"Assigned paper: {p['paper_id']} — {p['paper_title']}\n<assigned_paper>\n{text}</assigned_paper>"}]
    for learner,reply in history:
        messages.extend([{'role':'user','content':learner},{'role':'assistant','content':reply}])
    messages.append({'role':'user','content':current_text})
    upper=sum(len(m['content'].encode())+32 for m in messages)
    if upper+spec.GENERATION['max_tokens']>120000: raise ValueError('Context safety budget exceeded; paper was not truncated')
    return messages,{'paper_id':p['paper_id'],'paper_text_version':p['full_text_version'],'paper_text_hash':p['full_text_hash'],'prompt_version':a['prompt_version'],'model_id':a['model_id'],'generation_settings':spec.GENERATION,'history_policy':'successful-current-period-and-in-stage-attempts-v2','grounding_mode':'full_text','retrieval_chunk_ids':[],'input_token_upper_bound':upper}

def parse_reply(raw):
    """Extract the single JSON object. Returns a dict with at least 'reply', or None."""
    if not raw: return None
    candidates=re.findall(r'```(?:json)?\s*(\{.*?\})\s*```',raw,re.DOTALL) or []
    if not candidates:
        i,j=raw.find('{'),raw.rfind('}')
        if i!=-1 and j>i: candidates=[raw[i:j+1]]
    for c in candidates:
        try: data=json.loads(c)
        except Exception: continue
        if isinstance(data,dict) and isinstance(data.get('reply'),str) and data['reply'].strip():
            return data
    return None

def provider(messages):
    from config import DEMO_MODE,OPENROUTER_API_KEY,OPENROUTER_BASE_URL
    if DEMO_MODE: return json.dumps({'classification':'NO_ATTEMPT','present_concepts':[],'missing_concepts':[],'misconception':'','sufficient':False,'reply':'AUTOMATED RESPONSE: In your own words, what do you think the paper mainly investigates and finds?'}),{}
    from openai import OpenAI
    if not OPENROUTER_API_KEY: raise RuntimeError('Selected OpenRouter provider is unavailable')
    response=OpenAI(api_key=OPENROUTER_API_KEY,base_url=OPENROUTER_BASE_URL,timeout=30,max_retries=0).chat.completions.create(messages=messages,**spec.GENERATION)
    text=response.choices[0].message.content
    if not text or not text.strip(): raise RuntimeError('Provider returned an empty response')
    return text,response.usage.model_dump() if response.usage else {}

def precheck(text):
    """Deterministic NO_ATTEMPT guard, applied before the LLM evaluator (structured only).
    Whole-message junk only; short meaningful sentences fall through (return None)."""
    t=' '.join((text or '').split()).strip().lower().strip('!?.')
    if not t or len(t)<=2 or not re.search(r'[a-z]',t): return 'NO_ATTEMPT'
    if t in mentor_rubric.NO_ATTEMPT_TOKENS: return 'NO_ATTEMPT'
    return None

def source_text(paper_id,stage):
    """Deterministic "Where should I look?" from the verified per-paper source map.
    Never invents a heading; falls back to a neutral concept cue. Returns (text, refs, paper)."""
    ps=paper_source_maps.pointers(paper_id,stage)
    if not ps:
        return ("Try returning to the paper and looking for "+paper_source_maps.fallback(stage)+". Use “View research paper” when you’re ready.",None,paper_id)
    shown=ps[:3]
    body='; '.join(f"{p['ref']} — {p['desc']}" for p in shown)
    refs=' | '.join(p['ref'] for p in shown)
    return ("You might look at: "+body+". Use “View research paper” if you’d like to check it — that’s your choice.",refs,paper_id)

def llm_help(a,stage,help_type,last_learner,last_reply,invoke=None):
    """Post-attempt help generated by the model, grounded in the paper, never the full answer."""
    invoke=invoke or provider
    r=mentor_rubric.stage_rubric(stage)
    intents={'explain_feedback':'Re-explain your PREVIOUS feedback in simpler, plainer language. Do not add new information and do not reveal the answer.',
             'hint':'Give ONE more targeted hint, stronger than before but still NOT the full answer; point toward one concept or where in the paper to look.',
             'example':'Give a brief paper-specific example that scaffolds the reasoning WITHOUT supplying the complete final answer.'}
    intent=intents.get(help_type,intents['hint'])
    p,text=source(a['paper_id'],a['paper_text_hash'])
    sysmsg=(RULES+'You are helping a learner working on the stage "'+r['label']+'". Acknowledge only what the learner actually wrote; never attribute content they did not write. Keep it to 2-4 sentences, one focused point. '+intent)
    msgs=[{'role':'system','content':sysmsg},{'role':'system','content':f"Assigned paper: {p['paper_id']} — {p['paper_title']}\n<assigned_paper>\n{text}</assigned_paper>"}]
    if last_learner: msgs.append({'role':'user','content':'My last answer: '+last_learner})
    if last_reply: msgs.append({'role':'assistant','content':last_reply})
    msgs.append({'role':'user','content':'['+help_type+' requested]'})
    try:
        raw,_=invoke(msgs); out=(parse_reply(raw) or {}).get('reply') or (raw.strip() if raw else None)
    except Exception: out=None
    return ((out or ('Look again at your last point and add the one piece that was missing. '+r['hint'])),None,None)

def scaffold(a,stage,help_type,pre,last_learner,last_reply,invoke=None):
    """Dispatch a help request. Pre-attempt help and source pointers are deterministic
    (no answer leak); post-attempt explain/hint/example are model-generated."""
    r=mentor_rubric.stage_rubric(stage)
    if help_type=='source_pointer': return source_text(a['paper_id'],stage)
    if pre:
        if help_type=='hint': return ('Here is a cue, not the answer. '+r['hint'],None,None)
        if help_type=='unsure': return ("That’s okay — you don’t need the full answer yet. Start with one small part. "+r['hint'],None,None)
        if help_type=='example': return (r['example'],None,None)
        return (r['explain'],None,None)  # explain_question (default)
    return llm_help(a,stage,help_type,last_learner,last_reply,invoke)

def respond(exchange_id,invoke=None):
    invoke=invoke or provider
    with store.transaction(True) as db:
        x=store.one(db,'SELECT * FROM v5_exchanges WHERE exchange_id=?',(exchange_id,))
        if not x: raise ValueError('Unknown exchange')
        if x['status']=='completed': return x
        store.current(x['participant_id'],f"{x['period']}_tutor",db)
        atts=store.stage_attempts(x['participant_id'],x['period'],db,exchange_id)
        todo=[att for att in atts if att['request_status'] in ('pending','error')]
        if not todo: raise ValueError('No attempt awaiting a response')
        att=todo[-1]
        a=store.assignment(x['participant_id'],x['period'],db)
        structured=a['condition']=='structured'
        # Deterministic NO_ATTEMPT guard: obvious junk skips the provider (no request row).
        det=precheck(att['learner_response']) if structured else None
        rid=None; messages=None
        if det!='NO_ATTEMPT':
            prior_requests=store.rows(db,'SELECT * FROM v5_requests WHERE exchange_id=?',(exchange_id,))
            if len(prior_requests)>=mentor_rubric.MENTOR_ATTEMPT_HARD_CAP+4: raise ValueError('Provider retry limit reached')
            # History: completed exchanges this period + successful earlier attempts of THIS stage.
            history=[(e['user_text'],e['assistant_text']) for e in store.exchanges(x['participant_id'],x['period'],db) if e['status']=='completed']
            history+=[(p['learner_response'],p['tutor_response']) for p in atts if p['request_status']=='success' and p['attempt_id']!=att['attempt_id'] and p['tutor_response']]
            messages,provenance=construct(a,history,att['learner_response'],x['structured_stage'],att['attempt_number'])
            provenance.update({k:a[k] for k in ('participant_id','period','release_id','sequence_id','condition','instrument_version')})
            provenance.update(user_message_id=x['user_message_id'],exchange_id=exchange_id,attempt_id=att['attempt_id'],attempt_number=att['attempt_number'])
            rid=store.uid(); store.insert(db,'v5_requests',dict(request_id=rid,exchange_id=exchange_id,retry_number=len(prior_requests),started_at=store.now(),status='pending',provenance_json=store.dumps(provenance)))
        store.run(db,"UPDATE v5_stage_attempts SET request_status='pending' WHERE attempt_id=?",(att['attempt_id'],))
    if det=='NO_ATTEMPT':
        raw=None;usage={};error=None
    else:
        try: raw,usage=invoke(messages); error=None
        except Exception as exc: raw=None;usage={};error=type(exc).__name__  # no credentials/provider bodies in error exports
    data=parse_reply(raw) if raw is not None else None
    # Only the structured mentor requires the JSON judgement; self-directed is free text.
    if error is None and det is None and raw is not None and structured and data is None: error='InvalidProviderJSON'
    with store.transaction(True) as db:
        at=store.now(); valid=True
        try: store.current(x['participant_id'],f"{x['period']}_tutor",db,at)
        except ValueError: valid=False
        status='error' if error else 'success' if valid else 'late'
        if rid: store.run(db,'UPDATE v5_requests SET status=?,finished_at=?,error_status=?,usage_json=? WHERE request_id=?',(status,at,error,store.dumps(usage),rid))
        if structured:
            if det=='NO_ATTEMPT':
                classification='NO_ATTEMPT'; sufficient=False
                reply="Let’s start with your own attempt — a section name or “not sure” isn’t enough here. "+mentor_rubric.stage_rubric(x['structured_stage'])['hint']
            else:
                d=data or {}
                reply=d.get('reply'); classification=d.get('classification'); sufficient=bool(d.get('sufficient'))
            present=store.dumps((data or {}).get('present_concepts') or []); missing=store.dumps((data or {}).get('missing_concepts') or []); misc=(data or {}).get('misconception') or None
            suff_val=(1 if sufficient else 0) if (data is not None or det=='NO_ATTEMPT') else None
            # Only GENUINE attempts (partial/substantive/misconception) count toward the
            # attempt limit; a hard cap on TOTAL submissions prevents a junk trap.
            genuine=sum(1 for pa in atts if pa['attempt_id']!=att['attempt_id'] and pa.get('classification') in mentor_rubric.GENUINE)+(1 if classification in mentor_rubric.GENUINE else 0)
            total=len(atts)
            if status=='success':
                complete=sufficient or genuine>=mentor_rubric.MENTOR_MAX_ATTEMPTS or total>=mentor_rubric.MENTOR_ATTEMPT_HARD_CAP
                reason='sufficient' if sufficient else ('max_attempts' if genuine>=mentor_rubric.MENTOR_MAX_ATTEMPTS else ('attempt_cap' if total>=mentor_rubric.MENTOR_ATTEMPT_HARD_CAP else None))
            else: complete=False; reason=None
        else:
            # Self-directed: accept a JSON reply if the model returned one, else the raw text.
            reply=(data.get('reply') if data else None) or (raw.strip() if raw else None)
            classification=None; present=None; missing=None; misc=None; suff_val=None
            complete=(status=='success'); reason='self_directed' if complete else None
        store.run(db,'UPDATE v5_stage_attempts SET classification=?,present_concepts_json=?,missing_concepts_json=?,misconception=?,sufficient=?,tutor_response=?,request_status=?,responded_at=?,completion_reason=? WHERE attempt_id=?',
                  (classification,present,missing,misc,suff_val,reply,status,at,reason if complete else None,att['attempt_id']))
        if status=='success' and complete:
            store.run(db,"UPDATE v5_exchanges SET status='completed',assistant_message_id=?,assistant_text=?,completed_at=? WHERE exchange_id=? AND status!='completed'",(store.uid(),reply,at,exchange_id))
        elif status!='success':
            store.run(db,"UPDATE v5_exchanges SET status='failed' WHERE exchange_id=? AND status!='completed'",(exchange_id,))
        return store.one(db,'SELECT * FROM v5_exchanges WHERE exchange_id=?',(exchange_id,))
