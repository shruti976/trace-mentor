#!/usr/bin/env python3
"""Hosted V5 acceptance with excluded records and a persisted revision gate."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import v5_store as s
from config import read_bool_setting,DATABASE_URL,DEMO_MODE
from v5_tutor import respond

def main():
    if DEMO_MODE: raise RuntimeError('Hosted acceptance requires the live provider, never demo responses')
    revision=os.environ.get('RENDER_GIT_COMMIT','local')
    with s.transaction(True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS v5_release_checks (revision TEXT PRIMARY KEY,release_id TEXT NOT NULL,status TEXT NOT NULL,checked_at TEXT NOT NULL,report_json TEXT NOT NULL)')
        old=s.one(db,'SELECT * FROM v5_release_checks WHERE revision=?',(revision,))
    if old and old['status']=='passed':print('Hosted V5 checks already passed for '+revision);return
    if read_bool_setting('V5_RECRUITMENT_OPEN'):raise RuntimeError('New revision must first be deployed with V5 enrollment closed')
    from scripts.check_v5_postgres import check
    if not DATABASE_URL:raise RuntimeError('Existing PostgreSQL database required for hosted release')
    check(DATABASE_URL)
    report={'revision':revision,'release_id':s.spec.RELEASE_ID,'provider':[],'synthetic_only':True}
    seen=set(); guard=0
    # Enroll excluded participants until every paper x condition combo is exercised.
    # A single block of 4 usually suffices, but pre-existing partial TEST blocks (from
    # researcher-mode test enrollments) can leave 4 participants covering only 2 combos,
    # so keep going (capped) until all 4 are seen.
    while len(seen)<4 and guard<12:
        guard+=1
        p=s.enroll('AUTOMATED-V5-'+s.uid(),'AUTOMATED HOSTED EXCLUDE',{'purpose':'hosted release verification'},is_test=True)
        for period in (1,2):
            with s.transaction(True) as db:
                a=s.assignment(p['participant_id'],period,db)
                if (a['paper_id'],a['condition']) in seen:continue
                s.run(db,'UPDATE v5_participants SET stage=?,stage_started_at=? WHERE participant_id=?',(f'{period}_tutor',s.now(),p['participant_id']))
            x=s.begin_exchange(p['participant_id'],period,'The paper has a limited evaluation scope. Explain what evidence supports that interpretation.')
            result=respond(x['exchange_id'])
            with s.transaction() as db:r=s.one(db,'SELECT status,error_status,usage_json FROM v5_requests WHERE exchange_id=?',(x['exchange_id'],))
            report['provider'].append({'paper':a['paper_id'],'condition':a['condition'],**r})
            if r['status']!='success':
                print('HOSTED PROVIDER FAILED '+json.dumps(report));raise RuntimeError('Hosted full-context provider check failed; keep recruitment closed')
            seen.add((a['paper_id'],a['condition']))
        s.advance(p['participant_id'],'withdrawal')
    if len(seen)!=4:raise RuntimeError('Missing paper/condition provider coverage')
    with s.transaction(True) as db:s.insert(db,'v5_release_checks',dict(revision=revision,release_id=s.spec.RELEASE_ID,status='passed',checked_at=s.now(),report_json=s.dumps(report)))
    print('HOSTED V5 PASS '+json.dumps(report))
if __name__=='__main__':main()
