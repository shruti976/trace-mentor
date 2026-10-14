"""Every test uses a disposable database patched before initialization."""
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
import v5_store as s
import v5_tutor as tutor
from v5_exports import export_data
class V5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.patch=patch.multiple(s.db_utils,DATABASE_URL='',EXPERIMENT_DB=Path(self.tmp.name)/'test.db');self.patch.start();self.addCleanup(self.patch.stop)
        s.initialize();s.install_release()
    def enroll(self,pid=None): return s.enroll(pid or s.uid(),'AUTOMATED V5 EXCLUDE',{},is_test=True)
    def stage(self,p,stage):
        with s.transaction(True) as db:s.run(db,'UPDATE v5_participants SET stage=?,stage_started_at=? WHERE participant_id=?',(stage,s.now(),p['participant_id']))
    def test_blocks_retry_cap_and_historical(self):
        ps=[self.enroll() for _ in range(8)]
        for block in set(p['randomization_block_id'] for p in ps):self.assertEqual({p['sequence_id'] for p in ps if p['randomization_block_id']==block},set(s.spec.SEQUENCES))
        self.assertEqual(self.enroll(ps[0]['participant_id'])['sequence_id'],ps[0]['sequence_id'])
        with s.transaction() as db:
            self.assertEqual(s.one(db,'SELECT COUNT(*) n FROM v5_participants WHERE is_test=0 AND is_pilot=0')['n'],0)
            for p in ps:
                aa=[s.assignment(p['participant_id'],i,db) for i in (1,2)]
                self.assertEqual({a['condition'] for a in aa},{'self_directed','structured'})
                self.assertEqual({a['paper_id'] for a in aa},{'paper_a','paper_b'})
    def test_scoring_prediction_trust_and_resume(self):
        p=self.enroll();pid=p['participant_id'];orders=p['option_order_json']
        for period,pred in ((1,0),(2,5)):
            self.stage(p,f'{period}_quiz')
            with s.transaction() as db:items=s.items(pid,period,db)
            for i in items:s.answer(pid,period,i['item_id'],i['correct_option_id'])
            s.advance(pid);s.prediction(pid,period,pred);s.prediction(pid,period,pred,True)
            with self.assertRaises(ValueError):s.prediction(pid,period,5-pred,True)
            for key in s.MEASURES:s.measure(pid,period,key,3)
        out=export_data()['periods'];self.assertEqual([r['absolute_calibration_error'] for r in out],[5,0]);self.assertEqual([r['trust_mean'] for r in out],[3,3])
        self.assertEqual(s.participant(pid)['option_order_json'],orders)
    def test_missing_is_not_zero(self):
        p=self.enroll();self.stage(p,'1_followup')
        with self.assertRaises(ValueError):s.measure(p['participant_id'],1,'trust_item_1',3)
        rs=export_data()['periods'];self.assertIsNone(rs[0]['predicted_score']);self.assertIsNone(rs[0]['actual_score']);self.assertIsNone(rs[0]['source_consultation_count'])
    def test_consultation_refresh_timeout(self):
        p=self.enroll();pid=p['participant_id'];self.stage(p,'1_tutor')
        s.consultation(pid,1,'attach','tab1',s.uid());event=s.uid()
        first=s.consultation(pid,1,'paper_open','tab1',event)
        self.assertEqual(first,s.consultation(pid,1,'paper_open','tab1',event))
        self.assertEqual(first,s.consultation(pid,1,'paper_open','tab1',s.uid()))
        s.consultation(pid,1,'paper_close','tab1',s.uid());second=s.consultation(pid,1,'paper_open','tab1',s.uid());self.assertNotEqual(first,second)
        s.consultation(pid,1,'attach','tab2',s.uid())
        with self.assertRaises(ValueError):s.consultation(pid,1,'paper_open','tab1',s.uid())
        r=export_data()['periods'][0];self.assertEqual(r['source_consultation_count'],2);self.assertIsNone(r['source_consultation_seconds']);self.assertEqual(r['source_consultation_complete'],0)
        s.consultation(pid,1,'paper_open','tab2',s.uid());p=s.participant(pid)
        s.advance(pid,'timeout',(s.dt(p['stage_started_at'])+s.timedelta(seconds=360)).isoformat())
        with s.transaction() as db:self.assertIsNone(s.active_open(pid,1,db))
        exported=export_data();self.assertEqual(exported['periods'][0]['source_consultation_complete'],1)
        self.assertEqual(exported['transitions'][0]['participant_id'],pid)
    def test_five_successful_exchanges_and_grounding(self):
        for p in [self.enroll() for _ in range(4)]:
            for period in (1,2):
                pid=p['participant_id'];self.stage(p,f'{period}_tutor')
                for n in range(5):
                    x=s.begin_exchange(pid,period,'Explain this passage '+str(n))
                    if n==0:
                        failed=tutor.respond(x['exchange_id'],lambda m:(_ for _ in ()).throw(RuntimeError('synthetic failure')))
                        self.assertEqual(failed['status'],'failed')
                        with self.assertRaises(ValueError):s.advance(pid)
                    result=tutor.respond(x['exchange_id'],lambda m:(json.dumps({'classification':'SUBSTANTIVE_ATTEMPT','present_concepts':['x'],'missing_concepts':[],'misconception':'','sufficient':True,'reply':'Synthetic feedback'}),{}));self.assertEqual(result['status'],'completed')
                    self.assertEqual(tutor.respond(x['exchange_id'])['assistant_message_id'],result['assistant_message_id'])
                with self.assertRaises(ValueError):s.begin_exchange(pid,period,'sixth')
                with s.transaction() as db:
                    a=s.assignment(pid,period,db); xs=s.exchanges(pid,period,db)
                    self.assertEqual([x['required_exchange_number'] for x in xs],[1,2,3,4,5])
                    self.assertEqual([x['structured_stage'] for x in xs],list(s.spec.MENTOR_STAGES) if a['condition']=='structured' else [None]*5)
                    messages,meta=tutor.construct(a,[],'Explain this paper',s.spec.MENTOR_STAGES[0] if a['condition']=='structured' else None)
                    context='\n'.join(m['content'] for m in messages)
                    for item in s.spec.BASELINE_ITEMS+[i for paper in s.spec.PAPERS.values() for i in paper['mcqs']]:
                        for text in [item['question_text']]+item['answer_options']+item['option_ids']:self.assertNotIn(text,context)
                    self.assertEqual(meta['grounding_mode'],'full_text')
                s.advance(pid)
    def test_freeze_tamper(self):
        with patch.object(s.spec,'snapshot',return_value={}):
            with self.assertRaises(ValueError):s.spec.frozen_manifest()
if __name__=='__main__':unittest.main()
