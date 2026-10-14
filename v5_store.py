"""Transactional V5 persistence. All assignments are resolved server-side."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import json,secrets,uuid
from pathlib import Path
import db_utils
from data import study_v5 as spec
from data import mentor_rubric

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())
def dt(s): return datetime.fromisoformat(s)
def dumps(x): return spec.canonical(x)
@contextmanager
def transaction(write=False):
    db=db_utils.get_connection()
    try:
        if not db_utils.using_postgres():
            db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA busy_timeout=30000')
            if write: db.execute('BEGIN IMMEDIATE')
        elif write:
            # One transactional advisory lock across enrollment and state mutations.
            db.execute('SELECT pg_advisory_xact_lock(50720260907)')
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally: db.close()
def run(db,sql,args=()): return db.execute(db_utils.db_query(sql),args)
def one(db,sql,args=()):
    row=run(db,sql,args).fetchone(); return dict(row) if row else None
def rows(db,sql,args=()): return [dict(r) for r in run(db,sql,args).fetchall()]
def insert(db,table,data):
    run(db,f"INSERT INTO {table} ({','.join(data)}) VALUES ({','.join('?' for _ in data)})",tuple(data.values()))
MIGRATIONS=('migrations/005_v5.sql','migrations/006_v6.sql','migrations/007_v7.sql')
def initialize():
    with transaction(True) as db:
        for migration in MIGRATIONS:
            for sql in (spec.ROOT/migration).read_text().split(';'):
                if sql.strip(): db.execute(sql)
    protect_immutability()
def install_release():
    m=spec.frozen_manifest()
    with transaction(True) as db:
        existing=one(db,'SELECT * FROM v5_releases WHERE release_id=?',(spec.RELEASE_ID,))
        if existing:
            if existing['instrument_hash']!=m['instrument_hash'] or existing['manifest_json']!=dumps(m): raise ValueError('Immutable release mismatch')
        else: insert(db,'v5_releases',dict(release_id=spec.RELEASE_ID,instrument_version=spec.INSTRUMENT_VERSION,instrument_hash=m['instrument_hash'],instrument_json=dumps(spec.snapshot()),manifest_json=dumps(m)))
def participant(pid,db=None):
    if db is not None: return one(db,'SELECT * FROM v5_participants WHERE participant_id=?',(pid,))
    with transaction() as c: return participant(pid,c)
def assignment(pid,period,db):
    row=one(db,'SELECT p.release_id,p.sequence_id,a.* FROM v5_periods a JOIN v5_participants p USING(participant_id) WHERE a.participant_id=? AND a.period=?',(pid,period))
    if not row: raise ValueError('Unknown period assignment')
    return row
def frozen(pid,db):
    row=one(db,'SELECT r.instrument_json FROM v5_releases r JOIN v5_participants p USING(release_id) WHERE participant_id=?',(pid,))
    return json.loads(row['instrument_json'])
def current(pid,stage,db,at=None):
    p=participant(pid,db); at=at or now()
    if not p or p['status']!='active' or p['stage']!=stage: raise ValueError('This stage is no longer active')
    seconds=spec.BUDGETS[stage.split('_')[-1]]
    if dt(at)>=min(dt(p['deadline']),dt(p['stage_started_at'])+timedelta(seconds=seconds)): raise ValueError('Stage deadline reached')
    return p

def enroll(pid,name,background,is_test=False,is_pilot=False,at=None):
    from config import read_bool_setting,IRB_AMENDMENT_APPROVED
    at=at or now()
    with transaction(True) as db:
        old=participant(pid,db)
        if old: return old
        if not (is_test or is_pilot):
            if not (read_bool_setting('RECRUITMENT_OPEN') and read_bool_setting('V5_RECRUITMENT_OPEN') and IRB_AMENDMENT_APPROVED): raise ValueError('Enrollment is closed')
            if spec.ENROLLMENT_CLOSE and dt(at)>=dt(spec.ENROLLMENT_CLOSE): raise ValueError('Enrollment cutoff reached')
        release=one(db,'SELECT * FROM v5_releases WHERE release_id=?',(spec.RELEASE_ID,))
        if not release: raise ValueError('Frozen release is not installed')
        kind='test' if is_test else 'pilot' if is_pilot else 'production'
        count=one(db,'SELECT COUNT(*) AS n FROM v5_participants WHERE release_id=? AND is_test=0 AND is_pilot=0',(spec.RELEASE_ID,))['n']
        if kind=='production' and count>=spec.ENROLLMENT_CAP: raise ValueError('Enrollment cap reached')
        blocks=rows(db,'SELECT b.*,COUNT(p.participant_id) AS used FROM v5_blocks b LEFT JOIN v5_participants p ON p.randomization_block_id=b.block_id WHERE b.release_id=? AND b.allocation_kind=? GROUP BY b.block_id,b.release_id,b.allocation_kind,b.sequence_json,b.created_at HAVING COUNT(p.participant_id)<4 ORDER BY b.created_at',(spec.RELEASE_ID,kind))
        if blocks: block=blocks[0]
        else:
            order=list(spec.SEQUENCES); secrets.SystemRandom().shuffle(order)
            block=dict(block_id=uid(),release_id=spec.RELEASE_ID,allocation_kind=kind,sequence_json=dumps(order),created_at=at)
            insert(db,'v5_blocks',block); block['used']=0
        slot=block['used']; sequence=json.loads(block['sequence_json'])[slot]
        instrument=json.loads(release['instrument_json']); orders={}
        for item in instrument['baseline']+[i for paper in instrument['papers'].values() for i in paper['mcqs']]:
            options=list(item['option_ids']); secrets.SystemRandom().shuffle(options); orders[item['item_id']]=options
        p=dict(participant_id=pid,release_id=spec.RELEASE_ID,sequence_id=sequence,randomization_block_id=block['block_id'],block_slot=slot,assigned_at=at,is_test=int(is_test),is_pilot=int(is_pilot),consented_at=at,consent_sha256=spec.CONSENT_SHA256,background_json=dumps(background),option_order_json=dumps(orders),stage='baseline',stage_started_at=at,deadline=(dt(at)+timedelta(minutes=45)).isoformat(),status='active')
        insert(db,'v5_participants',p); insert(db,'v5_identities',dict(participant_id=pid,name=name))
        provenance=json.loads(release['manifest_json'])['papers']
        for period,(paper,condition) in enumerate(spec.SEQUENCES[sequence],1):
            insert(db,'v5_periods',dict(participant_id=pid,period=period,paper_id=paper,condition=condition,instrument_version=spec.INSTRUMENT_VERSION,prompt_version=spec.PROMPT_VERSION,model_id=spec.MODEL_ID,paper_text_version=provenance[paper]['full_text_version'],paper_text_hash=provenance[paper]['full_text_hash']))
        return participant(pid,db)

def items(pid,period,db):
    s=frozen(pid,db)
    return s['baseline'] if period is None else s['papers'][assignment(pid,period,db)['paper_id']]['mcqs']
def answer(pid,period,item_id,option):
    with transaction(True) as db:
        p=current(pid,'baseline' if period is None else f'{period}_quiz',db)
        item=next(i for i in items(pid,period,db) if i['item_id']==item_id)
        if option not in item['option_ids']: raise ValueError('Unknown stable option ID')
        at=now(); value=(pid,period,item_id,option,int(option==item['correct_option_id']),at,(dt(at)-dt(p['stage_started_at'])).total_seconds())
        run(db,'INSERT INTO v5_responses VALUES (?,?,?,?,?,?,?) ON CONFLICT(participant_id,item_id) DO UPDATE SET selected_option_id=excluded.selected_option_id,correct=excluded.correct,submitted_at=excluded.submitted_at,stage_elapsed_seconds=excluded.stage_elapsed_seconds',value)
def score(pid,period,db):
    rs=rows(db,'SELECT * FROM v5_responses WHERE participant_id=? AND '+('period IS NULL' if period is None else 'period=?'),(pid,) if period is None else (pid,period))
    return sum(r['correct'] for r in rs) if {r['item_id'] for r in rs}=={i['item_id'] for i in items(pid,period,db)} else None

def prediction(pid,period,value,submit=False):
    if type(value) is not int or not 0<=value<=5: raise ValueError('Prediction must be an integer 0–5')
    with transaction(True) as db:
        current(pid,f'{period}_followup',db)
        old=one(db,'SELECT * FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period))
        if old and old['prediction_timestamp']:
            if old['predicted_score']!=value: raise ValueError('Prediction is locked')
            return
        run(db,'INSERT INTO v5_predictions(participant_id,period,draft_score,predicted_score,actual_score,prediction_timestamp) VALUES (?,?,?,?,?,?) ON CONFLICT(participant_id,period) DO UPDATE SET draft_score=excluded.draft_score,predicted_score=excluded.predicted_score,actual_score=excluded.actual_score,prediction_timestamp=excluded.prediction_timestamp',(pid,period,value,value if submit else None,score(pid,period,db) if submit else None,now() if submit else None))
MEASURES={'mental_effort':9,'helpfulness':7,'verification_rating':5,'trust_item_1':7,'trust_item_2':7,'trust_item_3':7}
def measure(pid,period,key,value):
    if key not in MEASURES or type(value) is not int or not 1<=value<=MEASURES[key]: raise ValueError('Invalid measure')
    with transaction(True) as db:
        current(pid,f'{period}_followup',db)
        pred=one(db,'SELECT prediction_timestamp FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period))
        if not pred or not pred['prediction_timestamp']: raise ValueError('Submit prediction first')
        run(db,'INSERT INTO v5_measures VALUES (?,?,?,?,?) ON CONFLICT(participant_id,period,item_name) DO UPDATE SET value=excluded.value,response_timestamp=excluded.response_timestamp',(pid,period,key,value,now()))
def active_open(pid,period,db):
    return one(db,"SELECT o.* FROM v5_consultation_events o WHERE o.participant_id=? AND o.period=? AND o.event_type='paper_open' AND NOT EXISTS(SELECT 1 FROM v5_consultation_events c WHERE c.consultation_session_id=o.consultation_session_id AND c.event_type='paper_close')",(pid,period))
def event(db,a,session,event_type,at,client_event_id,reason=None,inferred=False):
    insert(db,'v5_consultation_events',{**{k:a[k] for k in ('participant_id','release_id','sequence_id','period','paper_id','condition')},'event_id':uid(),'consultation_session_id':session,'event_type':event_type,'timestamp':at,'received_at':now(),'timestamp_source':'inferred_bound' if inferred else 'server_transition' if reason else 'server_received','close_reason':reason,'is_inferred':int(inferred),'client_event_id':client_event_id})
def close_interval(db,pid,period,at,reason,inferred=False):
    opened=active_open(pid,period,db)
    if opened: event(db,assignment(pid,period,db),opened['consultation_session_id'],'paper_close',max(at,opened['timestamp']),uid(),reason,inferred)
def consultation(pid,period,action,tab,client_event_id):
    with transaction(True) as db:
        existing=one(db,'SELECT * FROM v5_consultation_events WHERE client_event_id=?',(client_event_id,))
        if existing: return existing['consultation_session_id']
        current(pid,f'{period}_tutor',db); a=assignment(pid,period,db); at=now()
        if action=='attach':
            if a['owner_tab']!=tab:
                close_interval(db,pid,period,a['last_observed_at'] or at,'refresh_or_tab_replaced',True)
            run(db,"UPDATE v5_periods SET owner_tab=?,last_observed_at=?,logging_coverage=CASE WHEN logging_coverage='incomplete' THEN 'incomplete' ELSE 'observed' END WHERE participant_id=? AND period=?",(tab,at,pid,period)); return None
        if a['owner_tab']!=tab: raise ValueError('Stale browser instance')
        run(db,'UPDATE v5_periods SET last_observed_at=? WHERE participant_id=? AND period=?',(at,pid,period))
        if action=='logging_gap':
            run(db,"UPDATE v5_periods SET logging_coverage='incomplete' WHERE participant_id=? AND period=?",(pid,period)); return None
        if action=='heartbeat': return None
        opened=active_open(pid,period,db)
        if action=='paper_open':
            if opened: return opened['consultation_session_id']
            session=uid(); event(db,a,session,'paper_open',at,client_event_id); return session
        if action in ('paper_close','unload'):
            if opened: event(db,a,opened['consultation_session_id'],'paper_close',at,client_event_id,action)
            return opened['consultation_session_id'] if opened else None
        raise ValueError('Unknown event action')

def exchanges(pid,period,db): return rows(db,'SELECT * FROM v5_exchanges WHERE participant_id=? AND period=? ORDER BY required_exchange_number',(pid,period))
def stage_attempts(pid,period,db,exchange_id=None):
    if exchange_id is not None: return rows(db,'SELECT * FROM v5_stage_attempts WHERE exchange_id=? ORDER BY attempt_number',(exchange_id,))
    return rows(db,'SELECT * FROM v5_stage_attempts WHERE participant_id=? AND period=? ORDER BY required_exchange_number,attempt_number',(pid,period))
def begin_exchange(pid,period,text):
    """Record one learner attempt on the current stage. Structured stages accept
    multiple attempts (revisions after feedback); self-directed exchanges complete
    on the first successful response. Every attempt is preserved in v5_stage_attempts."""
    text=text.strip()
    if not text or len(text)>4000: raise ValueError('Enter 1–4000 characters')
    with transaction(True) as db:
        current(pid,f'{period}_tutor',db); a=assignment(pid,period,db); prior=exchanges(pid,period,db)
        completed=[x for x in prior if x['status']=='completed']
        if len(completed)>=5: raise ValueError('Five exchanges already completed')
        number=len(completed)+1
        x=next((e for e in prior if e['status']!='completed'),None)
        if x is None:
            x=dict(exchange_id=uid(),participant_id=pid,period=period,required_exchange_number=number,user_message_id=uid(),structured_stage=spec.MENTOR_STAGES[number-1] if a['condition']=='structured' else None,user_text=text,submitted_at=now(),status='pending')
            insert(db,'v5_exchanges',x)
        atts=stage_attempts(pid,period,db,x['exchange_id'])
        last=atts[-1] if atts else None
        if last and last['request_status']=='pending' and (dt(now())-dt(last['submitted_at'])).total_seconds()<45:
            raise ValueError('This exchange is still processing')
        # A revision after successful-but-insufficient feedback is a NEW attempt.
        # A provider failure is retried on the SAME attempt (no duplicate learner message).
        if last and last['request_status']=='error':
            att=last
        else:
            n=len(atts)+1
            att=dict(attempt_id=uid(),exchange_id=x['exchange_id'],participant_id=pid,period=period,required_exchange_number=x['required_exchange_number'],structured_stage=x['structured_stage'],condition=a['condition'],attempt_number=n,learner_response=text,hint_level=n-1,request_status='pending',model_id=a['model_id'],prompt_version=a['prompt_version'],submitted_at=now())
            insert(db,'v5_stage_attempts',att)
        run(db,"UPDATE v5_exchanges SET user_text=?,status='pending' WHERE exchange_id=?",(text,x['exchange_id']))
        result=one(db,'SELECT * FROM v5_exchanges WHERE exchange_id=?',(x['exchange_id'],))
        result['attempt_id']=att['attempt_id']; result['attempt_number']=att['attempt_number']
        return result

def scaffold_events(pid,period,db):
    return rows(db,'SELECT * FROM v5_scaffold_events WHERE participant_id=? AND period=? ORDER BY created_at',(pid,period))
def stage_state(pid,period,db):
    """Current structured stage (1-5), its open exchange, attempts, and answered attempts."""
    xs=exchanges(pid,period,db); completed=[x for x in xs if x['status']=='completed']
    number=min(len(completed)+1,5)
    open_x=next((e for e in xs if e['status']!='completed'),None)
    atts=stage_attempts(pid,period,db,open_x['exchange_id']) if open_x else []
    answered=[a for a in atts if a.get('tutor_response')]
    return dict(number=number,exchange=open_x,attempts=atts,answered=answered,completed=len(completed))
def request_help(pid,period,help_type,generate):
    """Record a structured-mentor help request and the scaffold shown. `generate` is a
    callback (a,stage,help_type,pre,last_learner,last_reply)->(text,pointer_ref,pointer_paper)
    run OUTSIDE the write lock (it may call the provider for post-attempt help)."""
    with transaction() as db:
        current(pid,f'{period}_tutor',db); a=assignment(pid,period,db)
        if a['condition']!='structured': raise ValueError('Help controls are structured-only')
        stt=stage_state(pid,period,db); stage=spec.MENTOR_STAGES[stt['number']-1]
        pre=len(stt['answered'])==0
        allowed=mentor_rubric.PRE_ATTEMPT_HELP if pre else mentor_rubric.POST_ATTEMPT_HELP
        if help_type not in allowed: raise ValueError('Help not available here')
        prior=[e for e in scaffold_events(pid,period,db) if e['required_exchange_number']==stt['number']]
        if len(prior)>=mentor_rubric.MENTOR_MAX_HELP: raise ValueError('Help limit reached for this stage')
        last_learner=stt['answered'][-1]['learner_response'] if stt['answered'] else None
        last_reply=stt['answered'][-1]['tutor_response'] if stt['answered'] else None
        ex_id=stt['exchange']['exchange_id'] if stt['exchange'] else None
        number=stt['number']; level=allowed[help_type][1]
    text,pointer_ref,pointer_paper=generate(a,stage,help_type,pre,last_learner,last_reply)
    with transaction(True) as db:
        current(pid,f'{period}_tutor',db)
        insert(db,'v5_scaffold_events',dict(event_id=uid(),participant_id=pid,period=period,paper_id=a['paper_id'],structured_stage=stage,required_exchange_number=number,exchange_id=ex_id,event_type='help_request',help_type=help_type,pre_attempt=int(pre),scaffold_level=level,attempt_number=len(stt['answered']),pointer_ref=pointer_ref,pointer_paper_id=pointer_paper,scaffold_text=text,model_id=a['model_id'],prompt_version=a['prompt_version'],created_at=now()))
    return text

def advance(pid,reason='continue',at=None):
    at=at or now()
    with transaction(True) as db:
        p=participant(pid,db)
        if not p or p['status']!='active': return p
        stage=p['stage']; period=int(stage[0]) if stage[0] in '12' else None
        deadline=min(dt(p['deadline']),dt(p['stage_started_at'])+timedelta(seconds=spec.BUDGETS[stage.split('_')[-1]]))
        if reason=='timeout':
            if dt(at)<deadline: raise ValueError('Timeout is premature')
            at=deadline.isoformat()
        elif reason!='withdrawal':
            current(pid,stage,db,at)
            if stage=='baseline' or stage.endswith('_quiz'):
                if score(pid,period,db) is None: raise ValueError('Answer all five questions')
            if stage.endswith('_tutor'):
                xs=exchanges(pid,period,db)
                if reason=='failure_continuation':
                    if not any(x['status']=='failed' for x in xs): raise ValueError('No terminal provider failure')
                elif sum(x['status']=='completed' for x in xs)!=5: raise ValueError('Complete five exchanges')
            if stage.endswith('_followup'):
                pred=one(db,'SELECT prediction_timestamp FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period))
                ms=rows(db,'SELECT item_name FROM v5_measures WHERE participant_id=? AND period=?',(pid,period))
                if not pred or not pred['prediction_timestamp'] or {r['item_name'] for r in ms}!=set(MEASURES): raise ValueError('Complete follow-up measures')
        if period and stage.endswith('_tutor'): close_interval(db,pid,period,at,reason)
        end=reason=='withdrawal' or dt(at)>=dt(p['deadline']) or stage=='final'
        target='completed' if end else spec.STAGES[spec.STAGES.index(stage)+1]
        status=('withdrawn' if reason=='withdrawal' else 'timeout' if dt(at)>=dt(p['deadline']) else 'completed') if end else 'active'
        insert(db,'v5_transitions',dict(event_id=uid(),participant_id=pid,from_stage=stage,to_stage=target,timestamp=at,reason=reason,stage_elapsed_seconds=max(0,(dt(at)-dt(p['stage_started_at'])).total_seconds())))
        run(db,'UPDATE v5_participants SET stage=?,stage_started_at=?,status=?,completed_at=? WHERE participant_id=?',(target,at,status,at if end else None,pid))
        return participant(pid,db)
def reconcile(pid):
    p=participant(pid)
    while p and p['status']=='active':
        end=min(dt(p['deadline']),dt(p['stage_started_at'])+timedelta(seconds=spec.BUDGETS[p['stage'].split('_')[-1]]))
        if dt(now())<end: break
        p=advance(pid,'timeout')
    return p

def protect_immutability():
    """Database-enforced immutable assignments and append-only raw events."""
    protected={'v5_releases':None,'v5_consultation_events':None,'v5_scaffold_events':None,'v5_participants':['participant_id','release_id','sequence_id','randomization_block_id','block_slot','assigned_at','is_test','is_pilot','consented_at','consent_sha256','option_order_json'],'v5_periods':['participant_id','period','paper_id','condition','instrument_version','prompt_version','model_id','paper_text_version','paper_text_hash'],'v5_stage_attempts':['participant_id','period','required_exchange_number','attempt_number','learner_response','submitted_at']}
    with transaction(True) as db:
        for table,columns in protected.items():
            if db_utils.using_postgres():
                check='TRUE' if columns is None else ' OR '.join(f'OLD.{c} IS DISTINCT FROM NEW.{c}' for c in columns)
                db.execute(f"CREATE OR REPLACE FUNCTION {table}_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP = 'DELETE' OR ({check}) THEN RAISE EXCEPTION 'immutable V5 record'; END IF; RETURN NEW; END $$")
                db.execute(f'DROP TRIGGER IF EXISTS protect_{table} ON {table}')
                db.execute(f'CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {table}_immutable()')
            else:
                check='1' if columns is None else ' OR '.join(f'OLD.{c} IS NOT NEW.{c}' for c in columns)
                db.execute(f"CREATE TRIGGER IF NOT EXISTS protect_{table}_update BEFORE UPDATE ON {table} WHEN {check} BEGIN SELECT RAISE(ABORT,'immutable V5 record'); END")
                db.execute(f"CREATE TRIGGER IF NOT EXISTS protect_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable V5 record'); END")
        # Once submitted, the prediction is immutable even through direct SQL.
        if db_utils.using_postgres():
            db.execute("CREATE OR REPLACE FUNCTION v5_prediction_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.prediction_timestamp IS NOT NULL THEN RAISE EXCEPTION 'locked prediction'; END IF; RETURN NEW; END $$")
            db.execute('DROP TRIGGER IF EXISTS protect_v5_prediction ON v5_predictions')
            db.execute('CREATE TRIGGER protect_v5_prediction BEFORE UPDATE OR DELETE ON v5_predictions FOR EACH ROW EXECUTE FUNCTION v5_prediction_immutable()')
        else:db.execute("CREATE TRIGGER IF NOT EXISTS protect_v5_prediction BEFORE UPDATE ON v5_predictions WHEN OLD.prediction_timestamp IS NOT NULL BEGIN SELECT RAISE(ABORT,'locked prediction'); END")
