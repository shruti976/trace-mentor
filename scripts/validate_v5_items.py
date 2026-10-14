#!/usr/bin/env python3
"""Formatting/integrity checks, not educational or psychometric validation."""
import sys,csv,json,itertools
from pathlib import Path
from difflib import SequenceMatcher
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import study_v5 as s

def all_items(): return s.BASELINE_ITEMS+[i for p in s.PAPERS.values() for i in p['mcqs']]
def report():
    findings=[]
    for i in all_items():
        def flag(code,severity='warning'): findings.append({'item_id':i['item_id'],'finding':code,'severity':severity})
        options=i['answer_options']; ids=i['option_ids']; key=i['correct_option_id']; lengths=list(map(len,options))
        if ids.count(key)!=1: flag('key_cardinality','error'); continue
        if len(ids)!=len(options) or len(set(ids))!=len(ids): flag('invalid_option_ids','error')
        n=ids.index(key)
        if lengths[n]==max(lengths): flag('key_longest')
        if lengths[n]==min(lengths): flag('key_shortest')
        if max(lengths)>2*max(1,min(lengths)): flag('extreme_length_imbalance')
        for a,b in itertools.combinations(options,2):
            if SequenceMatcher(None,a.lower(),b.lower()).ratio()>.85: flag('near_duplicate_options')
        if not i.get('source_evidence'): flag('missing_evidence','error')
        if not i.get('key_rationale') or len(i.get('distractor_rationales',[]))!=len(ids)-1 or not all(i.get('distractor_rationales',[])): flag('missing_rationales','error')
        learner=' '.join([i['question_text']]+options)
        if any(x in learner for x in ids+['correct_option_id','key_rationale','answer key:']): flag('learner_metadata_leak','error')
    return findings

def main():
    output=s.ROOT/'docs/v5'; output.mkdir(exist_ok=True)
    findings=report(); (output/'item_quality.json').write_text(json.dumps({'status':'automated_only','findings':findings,'authoring_key_positions':[i['option_ids'].index(i['correct_option_id'])+1 for i in all_items()],'display_pattern_status':'requires enrolled option permutations; authoring order is not display order'},indent=2)+'\n')
    columns=['item_id','category','stem','options','proposed_key','source_evidence','key_rationale','distractor_rationales','reviewer_correctness','reviewer_ambiguity','reviewer_alignment','reviewer_distractor_quality','reviewer_comments','reviewer_name_or_code','review_date']
    sheet=[]
    for i in all_items(): sheet.append(dict(item_id=i['item_id'],category=i['question_category'],stem=i['question_text'],options=json.dumps(dict(zip(i['option_ids'],i['answer_options']))),proposed_key=i['correct_option_id'],source_evidence=i['source_evidence'],key_rationale=i['key_rationale'],distractor_rationales=json.dumps(dict(zip([x for x in i['option_ids'] if x!=i['correct_option_id']],i['distractor_rationales'])))))
    with (output/'item_review.csv').open('w') as f:
        writer=csv.DictWriter(f,columns);writer.writeheader();writer.writerows(sheet)
    (output/'item_review.md').write_text('# Independent item review — pending\n\nAutomated checks are not expert or educational validation. Complete all reviewer fields in the CSV.\n\n'+'\n\n'.join('## '+r['item_id']+'\n\n'+'\n\n'.join(f'**{c}**: {r.get(c,"Pending human review")}' for c in columns[1:]) for r in sheet))
    print(f'{len(all_items())} unchanged items; {len(findings)} findings; human review pending')
if __name__=='__main__': main()
