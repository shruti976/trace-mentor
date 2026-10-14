import concurrent.futures,json,sqlite3
from unittest.mock import patch
from tests.test_v5 import V5Tests
import v5_store as s
from v5_gateway import token,verify
class V5Acceptance(V5Tests):
    def test_concurrent_cap_deadline_and_exclusion(self):
        def enroll(n):
            try:return s.enroll('real-'+str(n),'AUTOMATED CONCURRENCY EXCLUDE',{},at='2026-09-07T12:00:00+00:00')
            except ValueError:return None
        with patch('config.IRB_AMENDMENT_APPROVED',True),patch('config.read_bool_setting',return_value=True):
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:ps=[p for p in pool.map(enroll,range(72)) if p]
            self.assertEqual(len(ps),60)
            with self.assertRaisesRegex(ValueError,'cap'):s.enroll('late','AUTOMATED EXCLUDE',{})
            pilot=s.enroll('pilot','AUTOMATED PILOT EXCLUDE',{},is_pilot=True)
            self.assertTrue(pilot['is_pilot'])
            for seq in s.spec.SEQUENCES:self.assertEqual(sum(p['sequence_id']==seq for p in ps),15)
    def test_enrollment_cutoff_is_optional_and_still_enforced_when_set(self):
        """Recruitment closes by researcher action; a configured date still rejects."""
        with patch('config.IRB_AMENDMENT_APPROVED',True),patch('config.read_bool_setting',return_value=True):
            self.assertIsNone(s.spec.ENROLLMENT_CLOSE)
            late=s.enroll('no-cutoff','AUTOMATED EXCLUDE',{},at='2027-06-01T12:00:00+00:00')
            self.assertEqual(late['participant_id'],'no-cutoff')
            with patch.object(s.spec,'ENROLLMENT_CLOSE','2026-01-01T00:00:00+00:00'):
                with self.assertRaisesRegex(ValueError,'cutoff'):s.enroll('after-cutoff','AUTOMATED EXCLUDE',{})
    def test_historical_rows_and_database_immutability(self):
        with s.transaction(True) as db:
            db.execute('CREATE TABLE legacy_fixture (id TEXT PRIMARY KEY, body TEXT)');db.execute("INSERT INTO legacy_fixture VALUES ('old','original historical content')")
        p=self.enroll();s.initialize();s.install_release()
        with s.transaction() as db:self.assertEqual(s.one(db,'SELECT * FROM legacy_fixture')['body'],'original historical content')
        for sql in ["UPDATE v5_participants SET is_pilot=1 WHERE participant_id=?","UPDATE v5_periods SET condition='structured' WHERE participant_id=?","DELETE FROM v5_participants WHERE participant_id=?"]:
            with self.assertRaises(Exception):
                with s.transaction(True) as db:s.run(db,sql,(p['participant_id'],))
    def test_tokens_and_direct_paper_equality(self):
        import v5_tutor as t
        p=self.enroll()
        with patch('v5_gateway.signing_key',return_value=b'test-only'):
            value=token(p['participant_id'],1,p['deadline']);self.assertEqual(verify(value)['period'],1)
            with self.assertRaises(ValueError):verify(value+'x')
        with s.transaction() as db:a=s.assignment(p['participant_id'],1,db)
        b={**a,'condition':'structured'};a={**a,'condition':'self_directed'}
        plain,_=t.construct(a,[],'Question');structured,_=t.construct(b,[],'Question',s.spec.MENTOR_STAGES[0])
        self.assertEqual(plain[1],structured[1]);self.assertNotIn('central_finding',plain[0]['content'])
        self.assertIn('Central claim',structured[0]['content'])
        hist,_=t.construct(b,[('my prior attempt','prior mentor feedback')],'Question',s.spec.MENTOR_STAGES[0])
        self.assertIn('prior mentor feedback',[m['content'] for m in hist])
        with self.assertRaises(ValueError):t.construct(b,[],'Question','not_a_stage')
    def test_late_provider_and_withdrawal(self):
        import v5_tutor as t
        p=self.enroll();pid=p['participant_id'];self.stage(p,'1_tutor')
        s.consultation(pid,1,'attach','tab',s.uid());s.consultation(pid,1,'paper_open','tab',s.uid())
        x=s.begin_exchange(pid,1,'Synthetic question')
        def late(messages):
            s.advance(pid,'withdrawal');return json.dumps({'classification':'SUBSTANTIVE_ATTEMPT','present_concepts':[],'missing_concepts':[],'misconception':'','sufficient':True,'reply':'Late synthetic feedback'}),{}
        result=t.respond(x['exchange_id'],late)
        self.assertEqual(result['status'],'failed')
        with s.transaction() as db:
            self.assertEqual(s.one(db,'SELECT status FROM v5_requests WHERE exchange_id=?',(x['exchange_id'],))['status'],'late')
            self.assertIsNone(s.active_open(pid,1,db))
        self.assertEqual(s.participant(pid)['status'],'withdrawn')
