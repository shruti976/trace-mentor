"""Participant interface for the isolated, frozen V5 release."""
import base64,json,secrets
import streamlit as st
from data import study_v5 as spec
from data import mentor_rubric
import v5_store as s
from v5_tutor import source,respond,scaffold
from v5_gateway import token
from config import ADMIN_ACCESS_TOKEN,DEMO_MODE
import hmac
consult_component=st.components.v2.component('v5_consultation',js=(spec.ROOT/'components/v5_consultation.js').read_text())

def guard(fn):
    """Run a stage-gated write from an implicit widget callback. If the stage has
    already advanced (e.g. the budget timer elapsed while the page sat idle), the
    write is moot: swallow it so the callback cannot crash the page. The 5s timer
    fragment reruns and moves the participant to the correct stage."""
    try:fn()
    except ValueError:pass

def select(label,key,options,saved,callback):
    if key not in st.session_state:st.session_state[key]=saved
    st.selectbox(label,[None]+list(options),key=key,format_func=lambda v:'Select a response' if v is None else str(v),on_change=lambda:guard(lambda:callback(st.session_state[key])) if st.session_state[key] is not None else None)

# V5-specific presentation. Injected separately from the shared v4 apply_style so the
# two conditions stay visually matched and v4 is untouched. Contains no color-only
# status cues (every state also carries text or a check mark).
_STYLE='''<style>
.v5-steps{display:flex!important;flex-direction:row!important;flex-wrap:nowrap;gap:.45rem;width:100%;margin:.15rem 0 1rem;padding:0;list-style:none}
.v5-stagebar{display:flex!important;flex-direction:row!important;flex-wrap:wrap;gap:.45rem;width:100%;margin:.15rem 0 .9rem;padding:0;list-style:none}
.v5-steps li{flex:1 1 auto;min-width:0;white-space:nowrap;border:1px solid #c7d4e5;border-radius:10px;padding:.5rem .75rem;font-size:.82rem;color:#40516a;background:#fff;text-align:center}
.v5-steps li .n{display:block;font-size:.64rem;letter-spacing:.07em;text-transform:uppercase;color:#8494ad;margin-bottom:.1rem}
.v5-steps li.done{background:#eef6ff;border-color:#9fb9e6;color:#1d4ed8}
.v5-steps li.now{background:#1d4ed8;border-color:#1d4ed8;color:#fff;font-weight:800}
.v5-steps li.now .n{color:#d5e3ff}
.v5-stagebar li{flex:0 0 auto;border:1px solid #c7d4e5;border-radius:20px;padding:.32rem .8rem;font-size:.82rem;color:#52627a;background:#fff}
.v5-stagebar li.done{border-color:#16705b;color:#125b4b;background:#effaf7}
.v5-stagebar li.now{border-color:#1d4ed8;color:#fff;background:#1d4ed8;font-weight:800}
[data-testid="stChatMessage"]{max-width:900px}
.v5-msg-label{font-size:.72rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#52627a;margin:-.15rem 0 .25rem}
.v5-timer{position:fixed;top:.55rem;left:50%;transform:translateX(-50%);z-index:9999;margin:0;padding:.42rem .95rem;border-radius:999px;background:#1d4ed8;border:1px solid #1d4ed8;color:#fff;font-weight:800;text-align:center;font-variant-numeric:tabular-nums;box-shadow:0 4px 16px rgba(20,33,61,.22);white-space:nowrap}
.v5-timer.low{background:#b3320f;border-color:#b3320f}
.v5-timer .t{font-size:1rem}
@media(max-width:720px){.v5-steps{flex-wrap:wrap}.v5-steps li{flex:1 1 30%;white-space:normal}}
</style>'''

_PHASES=['Introduction','Baseline','Paper 1','Paper 2','Final survey','Complete']
def study_progress(stage):
    """Neutral overall study progress, identical in both conditions. Never reveals condition."""
    if stage in (None,'introduction'):idx=0
    elif stage=='baseline':idx=1
    elif stage and stage[0] in '12':idx=int(stage[0])+1
    elif stage=='final':idx=4
    elif stage in ('completed','timeout','withdrawn'):idx=5
    else:idx=1
    lis=[]
    for i,name in enumerate(_PHASES):
        cls='done' if i<idx else 'now' if i==idx else ''
        cur=' aria-current="step"' if i==idx else ''
        mark='✓ ' if i<idx else ''
        lis.append(f'<li class="{cls}"{cur}><span class="n">Step {i+1}</span>{mark}{name}</li>')
    st.markdown(f'<ol class="v5-steps" aria-label="Study progress">{"".join(lis)}</ol>',unsafe_allow_html=True)

_STAGE_LABELS=['Claim','Method','Evidence','Limitations','Interpretation']
def stage_progress(completed):
    """Structured-condition reasoning-stage scaffold (part of the intervention). Completion only — never correctness."""
    lis=[]
    for i,name in enumerate(_STAGE_LABELS):
        cls='done' if i<completed else 'now' if i==completed else ''
        cur=' aria-current="step"' if i==completed else ''
        mark='✓ ' if i<completed else f'{i+1} '
        lis.append(f'<li class="{cls}"{cur}>{mark}{name}</li>')
    st.markdown(f'<ol class="v5-stagebar" aria-label="Reasoning stages">{"".join(lis)}</ol>',unsafe_allow_html=True)

def chat_turn(role,label,text):
    with st.chat_message(role):
        st.markdown(f'<div class="v5-msg-label">{label}</div>',unsafe_allow_html=True);st.write(text)
def onboarding():
    st.title('AI Research Reading Study')
    study_progress(None)
    st.write('Read two AI research papers and use an assistant with each. Each discussion includes five exchanges. Allow up to 45 minutes.')
    st.download_button('Read the consent document',spec.CONSENT_PATH.read_bytes(),file_name='study-consent.pdf',mime='application/pdf')
    consent=st.checkbox('I have read the consent document and agree to participate.')
    name=st.text_input('Name (restricted researcher access)')
    labels={'academic_level':['Undergraduate','Masters','Doctoral','Other'],'academic_field':['Computer science / AI','Engineering','Sciences','Humanities / social sciences','Other'],'prior_ai_coursework':['None','One course','More than one course'],'llm_use_frequency':['Never','Less than weekly','Weekly','Daily'],'prior_llm_research_familiarity':['None','A little','Moderate','Extensive']}
    values={k:st.selectbox(k.replace('_',' ').capitalize(),[None]+v,format_func=lambda x:'Select' if x is None else x) for k,v in labels.items()}
    test=False;pilot=False
    with st.expander('Researcher test / excluded pilot access'):
        credential=st.text_input('Researcher access token',type='password')
        authorized=bool(ADMIN_ACCESS_TOKEN and hmac.compare_digest(credential,ADMIN_ACCESS_TOKEN)) or DEMO_MODE
        if authorized:
            mode=st.selectbox('Enrollment type',['Production','AUTOMATED TEST EXCLUDE','Excluded human pilot']);test=mode=='AUTOMATED TEST EXCLUDE';pilot=mode=='Excluded human pilot'
    if st.button('Begin study',disabled=not(consent and name.strip() and all(v is not None for v in values.values()))):
        pid=st.session_state.setdefault('enrollment_id',s.uid())
        try:
            p=s.enroll(pid,name,values,is_test=test,is_pilot=pilot);st.query_params['participant_id']=p['participant_id'];st.rerun()
        except ValueError as exc:st.error(str(exc))

def quiz(p,period):
    pid=p['participant_id'];st.subheader('Baseline questions' if period is None else 'Paper questions')
    if period:st.info('Close outside paper tabs and other resources. The paper and assistant are unavailable during this quiz.')
    with s.transaction() as db:
        questions=s.items(pid,period,db);rs={r['item_id']:r['selected_option_id'] for r in s.rows(db,'SELECT * FROM v5_responses WHERE participant_id=?',(pid,))}
    order=json.loads(p['option_order_json'])
    for item in questions:
        key=f"{pid}:{item['item_id']}";options=order[item['item_id']];labels=dict(zip(item['option_ids'],item['answer_options']))
        if key not in st.session_state:st.session_state[key]=rs.get(item['item_id'])
        st.radio(item['question_text'],options,index=None,key=key,format_func=labels.get,on_change=lambda i=item,k=key:guard(lambda:s.answer(pid,period,i['item_id'],st.session_state[k])))
    if st.button('Submit answers',disabled=any(st.session_state.get(f"{pid}:{i['item_id']}") is None for i in questions)):s.advance(pid);st.rerun()

def paper_view(p,period,tutor=False):
    with s.transaction() as db:a=s.assignment(p['participant_id'],period,db)
    provenance,text=source(a['paper_id'],a['paper_text_hash']);st.subheader(provenance['paper_title'])
    if tutor:
        consult_component(data={'participant_id':p['participant_id'],'period':period,'token':token(p['participant_id'],period,p['deadline']),'title':provenance['paper_title'],'text':text,'pdf_data':'data:application/pdf;base64,'+base64.b64encode((spec.ROOT/provenance['source_pdf']).read_bytes()).decode()},key=f'consult:{period}')
    else:
        mode=st.radio('Paper presentation',['Readable full text','PDF'],horizontal=True)
        if mode=='PDF':st.pdf(str(spec.ROOT/provenance['source_pdf']),height=650)
        else:st.text(text)
    return a

_HELP_LABELS={**{k:v[0] for k,v in mentor_rubric.PRE_ATTEMPT_HELP.items()},**{k:v[0] for k,v in mentor_rubric.POST_ATTEMPT_HELP.items()}}
def help_controls(pid,period,atts,pending):
    stage_atts=[x for x in atts if pending and x['exchange_id']==pending['exchange_id']] if pending else []
    answered=[x for x in stage_atts if x.get('tutor_response')]
    pre=len(answered)==0
    controls=mentor_rubric.PRE_ATTEMPT_HELP if pre else mentor_rubric.POST_ATTEMPT_HELP
    st.caption('Need a nudge? These do not open the paper or give the answer.')
    cols=st.columns(len(controls))
    for col,(ht,(label,_)) in zip(cols,controls.items()):
        if col.button(label,key=f'help:{period}:{ht}:{len(stage_atts)}',use_container_width=True):
            try:
                with st.spinner('Preparing help…'):s.request_help(pid,period,ht,scaffold)
                st.rerun()
            except ValueError as exc:st.error(str(exc))

def tutoring(p,period):
    a=paper_view(p,period,True);pid=p['participant_id']
    st.caption('The AI assistant is grounded in the assigned paper. It may still misinterpret information or miss details contained in figures and tables. You can reopen the paper at any time.')
    structured=a['condition']=='structured'
    with s.transaction() as db:
        xs=s.exchanges(pid,period,db); atts=s.stage_attempts(pid,period,db)
        scaffolds=s.scaffold_events(pid,period,db) if structured else []
    completed=sum(x['status']=='completed' for x in xs)
    if structured:stage_progress(completed)
    else:st.caption(f'Exchange {completed} of 5 completed')
    # Chronological transcript: answered attempts + help scaffolds interleaved.
    timeline=[(att['responded_at'] or att['submitted_at'],'attempt',att) for att in atts if att.get('tutor_response')]
    timeline+=[(e['created_at'],'help',e) for e in scaffolds]
    for _,kind,item in sorted(timeline,key=lambda t:t[0] or ''):
        if kind=='attempt':
            chat_turn('user','You',item['learner_response']);chat_turn('assistant','Research assistant',item['tutor_response'])
        else:
            chat_turn('assistant','Mentor · '+_HELP_LABELS.get(item['help_type'],'help'),item['scaffold_text'])
    pending=next((x for x in xs if x['status']!='completed'),None)
    last=next((att for att in reversed(atts) if pending and att['exchange_id']==pending['exchange_id']),None) if pending else None
    failed=bool(pending and (pending['status']=='failed' or (last and last['request_status'] in ('error','pending'))))
    if completed<5:
        if structured:
            st.info(spec.MENTOR_QUESTIONS[spec.MENTOR_STAGES[completed]]+' Answer in your own words — two to four sentences is plenty.')
            help_controls(pid,period,atts,pending)
        else:
            st.info('Ask any question you choose about this paper. Complete five exchanges with the assistant.')
        if failed:
            st.warning('The assistant could not respond. Your progress has been saved. Failed or interrupted requests do not count toward your attempts.')
            if st.button('Retry'):
                try:
                    with st.spinner('Generating response…'):respond(pending['exchange_id'])
                    st.rerun()
                except ValueError as exc:st.error(str(exc))
            if pending['status']=='failed' and st.button('Continue after assistant failure'):
                s.advance(pid,'failure_continuation');st.rerun()
        else:
            text=st.chat_input('Your response' if structured else 'Your response or question',max_chars=4000)
            if text:
                try:
                    x=s.begin_exchange(pid,period,text)
                    with st.spinner('Generating response…'):respond(x['exchange_id'])
                    st.rerun()
                except ValueError as exc:st.error(str(exc))
    if completed==5:st.success('You have completed this discussion. Next, you will answer five questions on your own. The paper and assistant will not be available during that section.')
    if st.button('Continue to questions',disabled=completed!=5):s.advance(pid);st.rerun()

def followup(p,period):
    pid=p['participant_id'];st.subheader('Paper follow-up')
    with s.transaction() as db:
        pred=s.one(db,'SELECT * FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period)) or {}
        ms={r['item_name']:r['value'] for r in s.rows(db,'SELECT * FROM v5_measures WHERE participant_id=? AND period=?',(pid,period))}
    if not pred.get('prediction_timestamp'):
        key=f'prediction:{period}'
        select('How many of the five questions do you think you answered correctly?',key,range(6),pred.get('draft_score'),lambda v:s.prediction(pid,period,v))
        if st.button('Submit prediction',disabled=st.session_state.get(key) is None):s.prediction(pid,period,st.session_state[key],True);st.rerun()
        return
    st.caption('Your prediction has been recorded. Think about the assistant you just used.')
    labels={'mental_effort':'How much mental effort did you invest in understanding this paper? (1 = very low, 9 = very high)','verification_rating':'While using the AI Assistant, how often did you return to the research paper to verify information provided by the AI? (1 = never, 5 = very often)','helpfulness':'How helpful was this assistant for understanding the paper? (1 = not at all, 7 = very helpful)'}
    for key in ('mental_effort','verification_rating','helpfulness'):select(labels[key],f'{period}:{key}',range(1,s.MEASURES[key]+1),ms.get(key),lambda v,k=key:s.measure(pid,period,k,v))
    st.caption('For the following three items: 1 = strongly disagree; 7 = strongly agree. Consider only the assistant you just used.')
    for key,item in spec.TRUST.items():select(item['question'],f'{period}:{key}',range(1,8),ms.get(key),lambda v,k=key:s.measure(pid,period,k,v))
    if st.button('Continue',disabled=any(st.session_state.get(f'{period}:{k}') is None for k in s.MEASURES)):s.advance(pid);st.rerun()

def final(p):
    pid=p['participant_id'];saved=json.loads(p['final_json'])
    def save(key,value):
        with s.transaction(True) as db:
            row=s.current(pid,'final',db);values=json.loads(row['final_json']);values[key]=value
            if key=='assistant_preference':values['preferred_condition']=s.assignment(pid,1 if value=='First assistant' else 2,db)['condition'] if value in ('First assistant','Second assistant') else value
            s.run(db,'UPDATE v5_participants SET final_json=? WHERE participant_id=?',(s.dumps(values),pid))
    fields={'assistant_preference':('Which assistant do you prefer?',['First assistant','Second assistant','Neither','No preference']),'prohibited_tool_report':('Did you use outside resources during the quizzes?',['Yes','No','Unsure']),'material_interruption':('Did a substantial interruption affect your session?',['Yes','No']),'noticed_ai_discrepancy':('Did you notice assistant information inconsistent with the paper?',['Yes','No','Unsure'])}
    for key,(label,options) in fields.items():select(label,'final:'+key,options,saved.get(key),lambda v,k=key:save(k,v))
    for key,label in [('ai_use_strategy_text','How did you use the assistants? (optional)'),('ai_discrepancy_text','Describe any discrepancy you noticed. (optional)'),('optional_comment','Other comments (optional)')]:
        widget='final:'+key
        if widget not in st.session_state:st.session_state[widget]=saved.get(key,'')
        st.text_area(label,key=widget,on_change=lambda k=key,w=widget:guard(lambda:save(k,st.session_state[w])))
    if st.button('Finish study',disabled=any(st.session_state.get('final:'+k) is None for k in fields)):s.advance(pid);st.rerun()

def main():
    from app_v4_crossover import apply_style
    apply_style();st.markdown(_STYLE,unsafe_allow_html=True);admin();pid=st.query_params.get('participant_id')
    if not pid:onboarding();return
    p=s.reconcile(pid)
    if not p:st.error('Session not found. Use your original study link.');return
    st.caption('Save this page link to resume. Your answers are saved; the timer continues while away.')
    if p['status']!='active':
        study_progress('completed')
        st.success('You have completed the study. Your responses have been saved — thank you for participating.');return
    if st.session_state.get('_researcher'):
        with st.sidebar:
            stop=st.checkbox('End this session (researcher)')
            if st.button('End participation',disabled=not stop):s.advance(pid,'withdrawal');st.rerun()
    @st.fragment(run_every=5)
    def timer():
        current=s.reconcile(pid)
        if current['stage']!=p['stage']:st.rerun()
        remaining=min(s.dt(p['deadline']),s.dt(p['stage_started_at'])+s.timedelta(seconds=spec.BUDGETS[p['stage'].split('_')[-1]]))-s.dt(s.now())
        secs=max(0,int(remaining.total_seconds()))
        cls='v5-timer low' if secs<=30 else 'v5-timer'
        st.markdown(f'<div class="{cls}">Time remaining in this stage — <span class="t">{secs//60}:{secs%60:02d}</span></div>',unsafe_allow_html=True)
    timer();stage=p['stage']
    study_progress(stage)
    if stage=='baseline':quiz(p,None)
    elif stage=='final':final(p)
    else:
        period=int(stage[0]);phase=stage.split('_')[1]
        if phase=='read':
            st.caption(f'Read the assigned paper for Paper {period}. When you are ready, continue to the assistant.')
            paper_view(p,period)
            if st.button('Continue to assistant'):s.advance(pid);st.rerun()
        elif phase=='tutor':tutoring(p,period)
        elif phase=='quiz':quiz(p,period)
        else:followup(p,period)

def admin():
    with st.sidebar.expander('Restricted researcher exports'):
        credential=st.text_input('Export access token',type='password')
        ok=bool(ADMIN_ACCESS_TOKEN and hmac.compare_digest(credential,ADMIN_ACCESS_TOKEN)) or DEMO_MODE
        st.session_state['_researcher']=ok
        if not ok:return
        st.warning('Chat and free-text exports require review before public sharing. Names remain restricted.')
        if st.button('Prepare V5 export archive'):
            import io,zipfile
            from v5_exports import export_data,csv_bytes
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
                for key,rs in export_data().items():z.writestr(key+'.csv',csv_bytes(rs))
            st.session_state['v5_export']=output.getvalue()
        if st.session_state.get('v5_export'):st.download_button('Download V5 data',st.session_state['v5_export'],'v5-research-data.zip','application/zip')
        st.markdown('**Study workbook (.xlsx)** — one file, organised by reporting construct. Generated live from the database.')
        mode=st.radio('Workbook mode',['De-identified','Restricted (includes names)'],horizontal=True)
        types=st.multiselect('Participant types',['PROD','TEST','PILOT'],default=['PROD'])
        comp_only=st.checkbox('Completed sessions only')
        if st.button('Prepare study workbook'):
            from v5_workbook import build_bytes
            wb,counts=build_bytes(restricted=mode.startswith('Restricted'),include=tuple(types) or ('PROD',),completed_only=comp_only)
            st.session_state['v5_workbook']=wb
            st.session_state['v5_workbook_name']=('RESTRICTED_' if mode.startswith('Restricted') else 'deidentified_')+'study_workbook.xlsx'
            st.caption(f"Prepared — PROD {counts['PROD']}, TEST {counts['TEST']}, PILOT {counts['PILOT']}, completed {counts['completed']}.")
        if st.session_state.get('v5_workbook'):
            st.download_button('Download study workbook',st.session_state['v5_workbook'],st.session_state.get('v5_workbook_name','study_workbook.xlsx'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        from scripts import migrate_v4
        original=migrate_v4.RELEASE_ID
        try:
            migrate_v4.RELEASE_ID=spec.RELEASE_ID;backup=migrate_v4.stored_backup()
            if backup:st.download_button('Download restricted pre-V5 backup',backup,'pre-v5-restricted-backup.zip','application/zip')
        finally:migrate_v4.RELEASE_ID=original
