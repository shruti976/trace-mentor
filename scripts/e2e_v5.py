#!/usr/bin/env python3
"""Four real UI journeys, with disposable AUTOMATED EXCLUDE participants."""
import os,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
work=tempfile.TemporaryDirectory(prefix='v5-e2e-')
os.environ.update(EXPERIMENT_DB_PATH=str(Path(work.name)/'study.db'),HUMAI_DATABASE_URL='',HUMAI_DEMO_MODE='true',HUMAI_V5_EVENT_SECRET='isolated-automated-test-secret')
import v5_store as s
s.initialize();s.install_release()
from streamlit.testing.v1 import AppTest
for p in [s.enroll(s.uid(),'AUTOMATED UI EXCLUDE',{},is_test=True) for _ in range(4)]:
    sys.modules.pop('app_v5',None)
    pid=p['participant_id'];app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30);app.query_params['participant_id']=pid;app.run()
    def check():
        if len(app.exception):raise RuntimeError(str(app.exception))
    def click(label):
        check();next(b for b in app.button if b.label==label).click().run();check()
    def questions():
        for radio in list(app.radio):
            item_id=radio.key.split(':',1)[1]
            radio.set_value(__import__('json').loads(s.participant(pid)['option_order_json'])[item_id][0]).run()
        click('Submit answers')
    questions()
    for period in (1,2):
        click('Continue to assistant')
        for n in range(5):app.chat_input[0].set_value('Explain this paper in more detail.').run();check()
        click('Continue to questions');questions()
        next(x for x in app.selectbox if 'five questions' in x.label).select(0 if period==1 else 5).run();click('Submit prediction')
        for select in list(app.selectbox):select.select(3).run();check()
        click('Continue')
    for select in list(app.selectbox):select.select(select.options[1]).run();check()
    click('Finish study')
    assert s.participant(pid)['status']=='completed'
    print('PASS UI',p['sequence_id'],pid)
from v5_exports import export_data
out=export_data();assert len(out['periods'])==8 and all(r['complete_pair'] for r in out['roster'])
print('ALL FOUR UI JOURNEYS PASSED; synthetic only')
