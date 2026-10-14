"""Adaptive structured mentor (v6): attempt-quality gate, revisions preserved,
progressive hinting, self-directed contrast, prompt contract, assessment isolation.

The model performs classification; these tests inject the JSON a well-formed model
would return and assert the STORE/FLOW guarantees plus the constructed-prompt
contract. Actual model refusal-to-fabricate is verified live in the deploy smoke."""
import json,unittest
from tests.test_v5 import V5Tests
import v5_store as s
import v5_tutor as tutor
from data import mentor_rubric

JUNK=['summary','methods','table 1','idk','.','asdf','give me the answer']

def model(classification,sufficient,reply='Please share your own brief attempt first.',present=None,missing=None,misc=''):
    payload={'classification':classification,'present_concepts':present or [],'missing_concepts':missing or [],'misconception':misc,'sufficient':sufficient,'reply':reply}
    return lambda messages:(json.dumps(payload),{})

class MentorTests(V5Tests):
    def condition_period(self,want):
        p=self.enroll();pid=p['participant_id']
        with s.transaction() as db:
            period=next(i for i in (1,2) if s.assignment(pid,i,db)['condition']==want)
        self.stage(p,f'{period}_tutor');return pid,period

    def test_no_attempt_holds_stage_and_preserves_raw(self):
        pid,period=self.condition_period('structured')
        x=s.begin_exchange(pid,period,'summary')
        r=tutor.respond(x['exchange_id'],model('NO_ATTEMPT',False,reply='In your own words, what does the paper mainly investigate and find?'))
        self.assertNotEqual(r['status'],'completed')  # weak input does NOT complete the stage
        with s.transaction() as db:
            xs=s.exchanges(pid,period,db);atts=s.stage_attempts(pid,period,db)
        self.assertEqual(sum(e['status']=='completed' for e in xs),0)
        self.assertEqual(len(atts),1)
        self.assertEqual(atts[0]['classification'],'NO_ATTEMPT')
        self.assertEqual(atts[0]['learner_response'],'summary')      # raw learner text preserved
        self.assertEqual(atts[0]['tutor_response'],r_reply(r,atts))  # reply passed through, not fabricated
        with self.assertRaises(ValueError):s.advance(pid)            # cannot advance the tutor stage

    def test_all_junk_inputs_are_gated(self):
        for junk in JUNK:
            pid,period=self.condition_period('structured')
            x=s.begin_exchange(pid,period,junk)
            tutor.respond(x['exchange_id'],model('NO_ATTEMPT',False))
            with s.transaction() as db:
                xs=s.exchanges(pid,period,db);atts=s.stage_attempts(pid,period,db)
            self.assertEqual(sum(e['status']=='completed' for e in xs),0,f'{junk!r} should NOT complete a stage')
            self.assertEqual(atts[-1]['learner_response'],junk)

    def test_revision_trail_then_sufficient_completes(self):
        pid,period=self.condition_period('structured')
        x1=s.begin_exchange(pid,period,'They interviewed blind artists.')
        self.assertEqual(x1['attempt_number'],1)
        tutor.respond(x1['exchange_id'],model('PARTIAL_ATTEMPT',False,reply='You named the participants; what did they DO and how was information collected?',present=['participants']))
        x2=s.begin_exchange(pid,period,'Semi-structured interviews with six blind artists plus a Midjourney image task.')
        self.assertEqual(x2['attempt_number'],2)                     # same stage, revision = attempt 2
        self.assertEqual(x1['exchange_id'],x2['exchange_id'])        # same exchange (stage)
        tutor.respond(x2['exchange_id'],model('SUBSTANTIVE_ATTEMPT',True,reply='That addresses the key point.'))
        with s.transaction() as db:
            xs=s.exchanges(pid,period,db);atts=s.stage_attempts(pid,period,db,x1['exchange_id'])
        self.assertEqual(sum(e['status']=='completed' for e in xs),1)             # stage completes on sufficiency
        self.assertEqual([a['learner_response'] for a in atts],
                         ['They interviewed blind artists.','Semi-structured interviews with six blind artists plus a Midjourney image task.'])  # INITIAL->REVISION reconstructable
        self.assertEqual(atts[-1]['completion_reason'],'sufficient')

    def test_progressive_hinting_and_max_attempts_release(self):
        pid,period=self.condition_period('structured')
        for i in range(mentor_rubric.MENTOR_MAX_ATTEMPTS):
            x=s.begin_exchange(pid,period,f'a genuine but partial idea number {i}')
            tutor.respond(x['exchange_id'],model('PARTIAL_ATTEMPT',False,reply=f'hint {i}'))
        with s.transaction() as db:
            xs=s.exchanges(pid,period,db);atts=s.stage_attempts(pid,period,db)
        self.assertEqual(sum(e['status']=='completed' for e in xs),1)             # released after MAX genuine attempts (no trap)
        self.assertEqual(len(atts),mentor_rubric.MENTOR_MAX_ATTEMPTS)
        self.assertEqual([a['hint_level'] for a in atts],list(range(mentor_rubric.MENTOR_MAX_ATTEMPTS)))  # escalating scaffold
        self.assertEqual(atts[-1]['completion_reason'],'max_attempts')

    def test_junk_does_not_count_as_genuine_but_hard_cap_releases(self):
        pid,period=self.condition_period('structured')
        cap=mentor_rubric.MENTOR_ATTEMPT_HARD_CAP
        for i in range(cap):
            with s.transaction() as db:
                self.assertEqual(sum(e['status']=='completed' for e in s.exchanges(pid,period,db)),0,f'junk completed early at {i}')
            x=s.begin_exchange(pid,period,'summary')
            tutor.respond(x['exchange_id'],model('SUBSTANTIVE_ATTEMPT',True,reply='ignored: deterministic'))  # model result ignored
        with s.transaction() as db:
            xs=s.exchanges(pid,period,db); atts=s.stage_attempts(pid,period,db)
        self.assertEqual(sum(e['status']=='completed' for e in xs),1)                 # released only at the hard cap
        self.assertEqual(atts[-1]['completion_reason'],'attempt_cap')
        self.assertTrue(all(a['classification']=='NO_ATTEMPT' for a in atts))         # every junk turn stayed NO_ATTEMPT

    def test_deterministic_precheck(self):
        for junk in JUNK+['I DK','n/a','...','ASDF']:
            self.assertEqual(tutor.precheck(junk),'NO_ATTEMPT',f'{junk!r} should precheck NO_ATTEMPT')
        for real in ['They interviewed six blind artists.','The paper introduces MODBENCH to evaluate LLM notes.']:
            self.assertIsNone(tutor.precheck(real),f'{real!r} should fall through to the evaluator')

    def test_self_directed_is_not_gated(self):
        pid,period=self.condition_period('self_directed')
        x=s.begin_exchange(pid,period,'summary')                     # same weak input as structured
        r=tutor.respond(x['exchange_id'],model('NO_ATTEMPT',False,reply='Here is an overview grounded in the paper...'))
        self.assertEqual(r['status'],'completed')                    # self-directed completes each exchange
        with s.transaction() as db:atts=s.stage_attempts(pid,period,db)
        self.assertIsNone(atts[0]['structured_stage'])               # no stage scaffold imposed
        self.assertEqual(atts[0]['completion_reason'],'self_directed')

    def test_prompt_contract_and_assessment_isolation(self):
        pid,period=self.condition_period('structured')
        with s.transaction() as db:a=s.assignment(pid,period,db)
        messages,meta=tutor.construct(a,[],'summary',s.spec.MENTOR_STAGES[0],1)
        context='\n'.join(m['content'] for m in messages)
        self.assertIn('NO_ATTEMPT',context)                          # gate instructed
        self.assertIn('never fabricate',context.lower())             # anti-fabrication rule present
        self.assertIn(mentor_rubric.stage_rubric('central_finding')['label'],context)  # rubric present
        for item in s.spec.BASELINE_ITEMS+[i for paper in s.spec.PAPERS.values() for i in paper['mcqs']]:
            for text in [item['question_text']]+item['answer_options']+item['option_ids']:
                self.assertNotIn(text,context)                       # NO assessment items/answers ever in context

    def test_help_controls_pre_and_post(self):
        pid,period=self.condition_period('structured')
        with s.transaction() as db: a=s.assignment(pid,period,db)
        # PRE-attempt: explain_question is deterministic and logged as pre_attempt
        txt=s.request_help(pid,period,'explain_question',tutor.scaffold)
        self.assertTrue(txt and 'MODBENCH' not in txt.upper())  # no paper answer leaked pre-attempt
        with s.transaction() as db: ev=s.scaffold_events(pid,period,db)
        self.assertEqual(ev[-1]['help_type'],'explain_question'); self.assertEqual(ev[-1]['pre_attempt'],1)
        # a POST-only control is rejected before any attempt
        with self.assertRaises(ValueError): s.request_help(pid,period,'example',tutor.scaffold)
        # source pointer is deterministic and tagged with the assigned paper
        s.request_help(pid,period,'source_pointer',tutor.scaffold)
        with s.transaction() as db: sp=[e for e in s.scaffold_events(pid,period,db) if e['help_type']=='source_pointer'][-1]
        self.assertEqual(sp['pointer_paper_id'],a['paper_id']); self.assertTrue(sp['pointer_ref'])
        # after an attempt, POST help is available and PRE-only is rejected
        x=s.begin_exchange(pid,period,'They ran interviews with six blind artists.')
        tutor.respond(x['exchange_id'],model('PARTIAL_ATTEMPT',False,reply='Good start.'))
        post=s.request_help(pid,period,'explain_feedback',lambda a,st,ht,pre,ll,lr:('simpler feedback',None,None))
        self.assertEqual(post,'simpler feedback')
        with s.transaction() as db: self.assertEqual(s.scaffold_events(pid,period,db)[-1]['pre_attempt'],0)
        with self.assertRaises(ValueError): s.request_help(pid,period,'explain_question',tutor.scaffold)  # pre-only now

    def test_source_pointers_are_paper_specific(self):
        ta,_,_=tutor.source_text('paper_a','methodology')
        tb,_,_=tutor.source_text('paper_b','methodology')
        self.assertIn('MODBench',ta); self.assertNotIn('Methods and Demographics',ta)   # no Paper B heading in Paper A
        self.assertIn('Methods and Demographics',tb); self.assertNotIn('MODBench',tb)   # no Paper A heading in Paper B
        # every stage's pointers for each paper reference only that paper's verified locations
        from data import paper_source_maps as maps
        for pid in ('paper_a','paper_b'):
            other='paper_b' if pid=='paper_a' else 'paper_a'
            for stage in s.spec.MENTOR_STAGES:
                text,_,_=tutor.source_text(pid,stage); mine={p['ref'] for p in maps.pointers(pid,stage)}
                for op in maps.pointers(other,stage):
                    if op['ref'] not in mine: self.assertNotIn(op['ref'],text)

    def test_help_does_not_open_paper(self):
        # requesting a source pointer must NOT create a consultation (paper-open) event
        pid,period=self.condition_period('structured')
        s.request_help(pid,period,'source_pointer',tutor.scaffold)
        with s.transaction() as db:
            self.assertIsNone(s.active_open(pid,period,db))
            self.assertEqual(s.rows(db,'SELECT COUNT(*) n FROM v5_consultation_events WHERE participant_id=?',(pid,))[0]['n'],0)

def r_reply(exchange_row,atts):
    # helper: the reply shown equals the stored tutor_response for the processed attempt
    return atts[-1]['tutor_response']

if __name__=='__main__':unittest.main()
