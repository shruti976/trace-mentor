#!/usr/bin/env python3
"""Four live requests, isolated synthetic participants, one per paper/condition."""
import os,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
with tempfile.TemporaryDirectory(prefix='v5-provider-') as work:
    os.environ.update(EXPERIMENT_DB_PATH=str(Path(work)/'study.db'),HUMAI_DATABASE_URL='',HUMAI_DEMO_MODE='false')
    import v5_store as s
    from v5_tutor import respond
    s.initialize();s.install_release();seen=set()
    for _ in range(4):
        p=s.enroll(s.uid(),'AUTOMATED LIVE PROVIDER EXCLUDE',{},is_test=True)
        for period in (1,2):
            with s.transaction(True) as db:
                a=s.assignment(p['participant_id'],period,db)
                if (a['paper_id'],a['condition']) in seen:continue
                s.run(db,'UPDATE v5_participants SET stage=?,stage_started_at=? WHERE participant_id=?',(f'{period}_tutor',s.now(),p['participant_id']))
            x=s.begin_exchange(p['participant_id'],period,'The paper studies a limited sample and its findings should be interpreted within that scope. Explain whether this is supported.')
            respond(x['exchange_id'])
            with s.transaction() as db:
                r=s.one(db,'SELECT * FROM v5_requests WHERE exchange_id=?',(x['exchange_id'],))
                att=s.stage_attempts(p['participant_id'],period,db,x['exchange_id'])[-1]
            if r['status']!='success' or not att['tutor_response']:
                print('REQUEST FAILURE',r['status'],r['error_status'],flush=True)
                raise RuntimeError('Live provider request failed')
            print('PASS LIVE',a['paper_id'],a['condition'],'classification',att['classification'],'response_chars',len(att['tutor_response']),'usage',r['usage_json'],flush=True)
            seen.add((a['paper_id'],a['condition']))
    assert len(seen)==4
