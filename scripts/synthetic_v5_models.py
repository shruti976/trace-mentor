#!/usr/bin/env python3
"""Known/null/missing/mixed-cohort fixtures; never participant evidence."""
import sys,csv,json,subprocess,os
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from data.study_v5 import SEQUENCES,RELEASE_ID
from v5_exports import csv_bytes

def fixture(path,effect=0,n=400,zero_counts=False):
    rng=np.random.default_rng(20260907);roster=[];periods=[];items=[];itemeffect=rng.normal(0,.8,10)
    for i in range(n):
        pid=f'SYNTHETIC-EXCLUDE-{i}';seq=list(SEQUENCES)[i%4];ability=rng.normal(0,.9);consult=rng.normal(0,.8);cal=rng.normal(0,.7)
        base={'participant_id':pid,'release_id':RELEASE_ID,'sequence_id':seq,'is_test':0,'is_pilot':0,'baseline_score':int(rng.binomial(5,.5)),'complete_pair':1,'session_completed':1}
        roster.append(base)
        for period,(paper,condition) in enumerate(SEQUENCES[seq],1):
            structured=condition=='structured';perioditems=[]
            for j in range(5):
                offset=j+(0 if paper=='paper_a' else 5);prob=1/(1+np.exp(-(.2+ability+itemeffect[offset]+effect*.8*structured)))
                correct=int(rng.binomial(1,prob));perioditems.append(correct)
                items.append({**base,'period':period,'paper_id':paper,'condition':condition,'item_id':paper+str(j),'correct':correct})
            actual=sum(perioditems);magnitude=int(np.clip(round(2+cal+rng.normal(0,.65)-effect*.8*structured),0,5));prediction=actual+magnitude if actual+magnitude<=5 else actual-magnitude if actual>=magnitude else 0
            count=int(rng.poisson(rng.gamma(2,np.exp(.8+consult+effect*.5*structured)/2)))
            periods.append({**base,'period':period,'paper_id':paper,'condition':condition,'actual_score':actual,'predicted_score':prediction,'source_consultation_count':0 if zero_counts else count,'absolute_calibration_error':abs(prediction-actual)})
    # Outcome-specific missingness and a historical row to test cohort isolation.
    for r in periods[-10:]:r['absolute_calibration_error']=None
    history={**roster[0],'participant_id':'SYNTHETIC-HISTORY','release_id':'old-release'};roster.append(history)
    path.mkdir(parents=True,exist_ok=True)
    for name,data in [('roster',roster),('periods',periods),('items',items)]: (path/(name+'.csv')).write_bytes(csv_bytes(data))
    (path/'SYNTHETIC.txt').write_text('All rows are generated software-test fixtures, not participant observations. is_test=0 exercises production-filter code in isolated files only.\n')

def main():
    root=Path('/tmp/v5-model-validation');reports={}
    for name,effect,zero in [('null',0,False),('known',1,False),('all_zero_counts',0,True)]:
        source=root/name/'input';out=root/name/'output';fixture(source,effect,zero_counts=zero)
        run=subprocess.run(['Rscript',str(ROOT/'analysis/analyze_v5.R'),str(source),str(out)],capture_output=True,text=True)
        if run.returncode:raise RuntimeError(run.stderr)
        results=list(csv.DictReader((out/'models.csv').open()));reports[name]=results
        if name=='known':
            for r in results:
                if r['hypothesis']=='H1':assert r['status']=='estimable' and float(r['estimate'])>1,r
                if r['hypothesis']=='H2':assert r['status']=='estimable' and float(r['estimate'])>1,r
                if r['hypothesis']=='H3':assert r['status']=='estimable' and float(r['estimate'])<0,r
        if zero:assert next(r for r in results if r['hypothesis']=='H2')['status']=='nonestimable'
        print('PASS SYNTHETIC',name,flush=True)
    (ROOT/'docs/v5/synthetic_model_checks.json').write_text(json.dumps({'synthetic_only':True,'reports':reports},indent=2)+'\n')
if __name__=='__main__':main()
