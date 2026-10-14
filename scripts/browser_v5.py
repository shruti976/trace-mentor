#!/usr/bin/env python3
"""Real Chromium gateway/lifecycle checks, isolated from research databases.

Every wait is anchored to persisted state rather than to rendered markup where possible:
Streamlit reruns replace DOM nodes on each widget callback, so a snapshot of element handles
goes stale mid-stage. Waiting on the database also makes each step prove that the participant
action was actually recorded, not merely clicked.
"""
import os,tempfile,sys,subprocess,time,socket,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
work=tempfile.TemporaryDirectory(prefix='v5-browser-');dbpath=str(Path(work.name)/'study.db')
os.environ.update(EXPERIMENT_DB_PATH=dbpath,HUMAI_DATABASE_URL='',HUMAI_DEMO_MODE='true',HUMAI_V5_EVENT_SECRET='isolated-browser-test-secret',PORT='8512')
import v5_store as s
s.initialize();s.install_release()
ps=[s.enroll(s.uid(),'AUTOMATED BROWSER EXCLUDE',{},is_test=True) for _ in range(8)]
from playwright.sync_api import sync_playwright
log=open('/tmp/v5-browser-server.log','w');server=subprocess.Popen([sys.executable,'v5_gateway.py'],cwd=ROOT,env=os.environ,stdout=log,stderr=log)

def until(check,description,seconds=45):
    deadline=time.time()+seconds
    while time.time()<deadline:
        try:
            if check():return True
        except (urllib.error.URLError,TimeoutError,OSError):
            pass
        time.sleep(.25)
    raise AssertionError('Timed out waiting for '+description)
def query(sql,args):
    with s.transaction() as db:return s.rows(db,sql,args)
def answered(pid): return len(query('SELECT item_id FROM v5_responses WHERE participant_id=?',(pid,)))
def measures(pid,period): return {r['item_name'] for r in query('SELECT item_name FROM v5_measures WHERE participant_id=? AND period=?',(pid,period))}
def completed(pid,period): return sum(x['status']=='completed' for x in query('SELECT status FROM v5_exchanges WHERE participant_id=? AND period=?',(pid,period)))
def stage(pid): return s.participant(pid)['stage']
def events(pid,period): return query('SELECT event_type,is_inferred,consultation_session_id FROM v5_consultation_events WHERE participant_id=? AND period=?',(pid,period))

try:
    # The gateway binds its own port immediately but proxies to a Streamlit child it spawns
    # separately; a request arriving before that child listens gets a proxy error and the
    # single-page shell never recovers. Wait for the composed service to actually serve.
    for port in (8501,8512):
        deadline=time.time()+90
        while time.time()<deadline:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.25):break
            except OSError:time.sleep(.25)
        else:raise AssertionError(f'Port {port} never accepted connections')
    until(lambda:urllib.request.urlopen('http://127.0.0.1:8512/',timeout=2).status==200,'gateway to serve the application shell',90)

    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--host-resolver-rules=MAP study.test 127.0.0.1'])
        for n,p in enumerate(ps):
            viewport={'width':1280,'height':800} if n<4 else {'width':390,'height':844}
            page=browser.new_page(viewport=viewport);pid=p['participant_id']
            page.on('pageerror',lambda error:print('BROWSER ERROR',str(error),flush=True))
            page.on('console',lambda message:print('BROWSER CONSOLE',message.type,message.text,flush=True) if message.type=='error' else None)
            page.set_default_timeout(45000)
            page.goto('http://study.test:8512/?participant_id='+pid)

            def boxes(): return page.locator('[role=combobox]')
            def pick(index,option):
                """Re-resolve the widget on every call: the previous callback reran the script."""
                until(lambda:boxes().count()>index,f'select box {index}')
                # Centre the widget first. Minimal scrolling leaves a low widget flush against the
                # foot of a phone viewport, where the option list has no room and does not open.
                boxes().nth(index).evaluate('el=>el.scrollIntoView({block:"center"})')
                page.wait_for_timeout(150)
                boxes().nth(index).click()
                page.get_by_role('listbox').wait_for()
                page.get_by_role('option',name=option,exact=True).click()
                page.get_by_role('listbox').wait_for(state='detached')
            def quiz():
                page.get_by_role('button',name='Submit answers',exact=True).wait_for()
                until(lambda:page.get_by_role('radiogroup').count()==5,'five rendered items')
                for i in range(5):
                    before=answered(pid)
                    # The keyed radio input is visually hidden; the label carries the click target.
                    page.get_by_role('radiogroup').nth(i).get_by_test_id('stRadioOption').first.click()
                    until(lambda b=before:answered(pid)==b+1,f'item {i+1} to persist')
                current=stage(pid)
                page.get_by_role('button',name='Submit answers',exact=True).click()
                until(lambda c=current:stage(pid)!=c,'the quiz stage to advance')

            quiz()
            for period in (1,2):
                page.get_by_role('button',name='Continue to assistant',exact=True).click()
                until(lambda:stage(pid)==f'{period}_tutor','the assistance stage')
                opened=page.get_by_role('button',name='Open full research paper',exact=True)
                opened.wait_for();opened.click()
                page.get_by_role('button',name='Close full paper and return to chat',exact=True).wait_for()
                until(lambda:sum(e['event_type']=='paper_open' for e in events(pid,period))==1,'the first consultation to be logged')
                # A refresh must reconcile the open interval and restore the viewer closed.
                page.reload()
                opened.wait_for();opened.click()
                until(lambda:sum(e['event_type']=='paper_open' for e in events(pid,period))==2,'a second consultation session after refresh')
                page.get_by_role('button',name='Close full paper and return to chat',exact=True).click()
                until(lambda:sum(e['event_type']=='paper_close' for e in events(pid,period))==2,'both consultation intervals to close')
                page.screenshot(path=f'/tmp/v5-browser-{n}-{period}.png',full_page=True)
                for k in range(5):
                    chat=page.get_by_placeholder('Your response or question')
                    chat.fill('Explain an important passage from the paper.');chat.press('Enter')
                    until(lambda k=k:completed(pid,period)==k+1,f'exchange {k+1} to complete')
                    page.get_by_text(f'Exchange {k+1} of 5 completed',exact=True).wait_for()
                page.get_by_role('button',name='Continue to questions',exact=True).click()
                until(lambda:stage(pid)==f'{period}_quiz','the paper quiz stage')
                quiz()
                until(lambda:stage(pid)==f'{period}_followup','the follow-up stage')
                pick(0,'0' if period==1 else '5')
                page.get_by_role('button',name='Submit prediction',exact=True).click()
                until(lambda:(query('SELECT prediction_timestamp FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period)) or [{}])[0].get('prediction_timestamp'),'the prediction to lock')
                page.get_by_text('Think about the assistant you just used.',exact=False).wait_for()
                until(lambda:boxes().count()==6,'six follow-up rating boxes')
                for i in range(6):
                    before=len(measures(pid,period))
                    pick(i,'3')
                    until(lambda b=before:len(measures(pid,period))==b+1,f'follow-up rating {i+1} to persist')
                assert measures(pid,period)==set(s.MEASURES),measures(pid,period)
                page.get_by_role('button',name='Continue',exact=True).click()
                until(lambda:stage(pid)!=f'{period}_followup','the follow-up stage to advance')

            until(lambda:stage(pid)=='final','the final survey')
            page.get_by_role('button',name='Finish study',exact=True).wait_for()
            until(lambda:boxes().count()==4,'four final survey questions')
            for i,(field,option) in enumerate([('assistant_preference','First assistant'),('prohibited_tool_report','No'),('material_interruption','No'),('noticed_ai_discrepancy','No')]):
                pick(i,option)
                until(lambda f=field:f in json.loads(s.participant(pid)['final_json']),f'{field} to persist')
            final=json.loads(s.participant(pid)['final_json'])
            with s.transaction() as db:first=s.assignment(pid,1,db)['condition']
            assert final['preferred_condition']==first,(final,first)
            page.get_by_role('button',name='Finish study',exact=True).click()
            page.get_by_text('Your session has ended',exact=False).wait_for()
            assert s.participant(pid)['status']=='completed'
            assert page.locator('body').evaluate('(el)=>el.scrollWidth<=window.innerWidth+2')
            print('PASS',p['sequence_id'],viewport,flush=True);page.close()
        browser.close()

    from v5_exports import export_data
    periods=export_data()['periods']
    assert len(periods)==16,len(periods)
    for r in periods:
        # The unload beacon may win the refresh race. Only inferred closures make duration missing.
        assert r['source_consultation_count']==2,r
        if r['consultation_inferred_close']:
            assert r['source_consultation_seconds'] is None,r
        else:
            assert r['source_consultation_seconds'] is not None,r
        assert r['consultation_unclosed_intervals']==0,r
        assert r['consultation_logging_coverage']=='observed',r
        assert r['completed_exchanges']==5 and r['discussion_sequence_completed']==1,r
        assert r['trust_mean']==3 and r['mental_effort']==3,r
        assert r['predicted_score']==(0 if r['period']==1 else 5),r
        assert r['absolute_calibration_error']==abs(r['predicted_score']-r['actual_score']),r
    print('EIGHT DESKTOP/MOBILE JOURNEYS AND CONSULTATION REFRESH PASSED',flush=True)
finally:
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill()
    log.close();work.cleanup()
