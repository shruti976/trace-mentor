"""V5 outcome grains, with raw missingness and no historical reconstruction."""
import csv,io,json
import v5_store as s

def export_data():
    result={k:[] for k in ('roster','periods','period1','items','consultation_events','exchanges','requests','stage_attempts','scaffold_events','pilot_items','display_patterns','measures','transitions')}
    with s.transaction() as db:
        active=s.rows(db,"SELECT participant_id FROM v5_participants WHERE release_id=? AND status='active'",(s.spec.RELEASE_ID,))
    for row in active:s.reconcile(row['participant_id'])
    with s.transaction() as db:
        ps=s.rows(db,'SELECT * FROM v5_participants WHERE release_id=?',(s.spec.RELEASE_ID,))
        for p in ps:
            pid=p['participant_id']; baseline=s.score(pid,None,db); out=[]
            base={k:p[k] for k in ('participant_id','release_id','sequence_id','is_test','is_pilot','status','randomization_block_id','assigned_at')}
            base['baseline_score']=baseline
            for period in (1,2):
                a=s.assignment(pid,period,db); actual=s.score(pid,period,db)
                pred=s.one(db,'SELECT * FROM v5_predictions WHERE participant_id=? AND period=?',(pid,period)) or {}
                measures={r['item_name']:r['value'] for r in s.rows(db,'SELECT * FROM v5_measures WHERE participant_id=? AND period=?',(pid,period))}
                ev=s.rows(db,'SELECT * FROM v5_consultation_events WHERE participant_id=? AND period=? ORDER BY timestamp,event_type DESC',(pid,period))
                opens={e['consultation_session_id']:e for e in ev if e['event_type']=='paper_open'}
                closes={e['consultation_session_id']:e for e in ev if e['event_type']=='paper_close'}
                ended=bool(s.one(db,'SELECT event_id FROM v5_transitions WHERE participant_id=? AND from_stage=?',(pid,f'{period}_tutor')))
                covered=a['logging_coverage']=='observed'
                inferred=any(e['is_inferred'] for e in ev)
                exact=covered and not inferred and set(opens)==set(closes)
                seconds=sum(max(0,(s.dt(closes[k]['timestamp'])-s.dt(o['timestamp'])).total_seconds()) for k,o in opens.items() if k in closes)
                predicted=pred.get('predicted_score'); error=predicted-actual if predicted is not None and actual is not None else None
                xs=s.exchanges(pid,period,db)
                r={**base,**{k:a[k] for k in ('period','paper_id','condition','instrument_version','prompt_version','model_id','paper_text_version','paper_text_hash')},'actual_score':actual,'predicted_score':predicted,'prediction_timestamp':pred.get('prediction_timestamp'),'signed_calibration_error':error,'absolute_calibration_error':abs(error) if error is not None else None,'source_consultation_count':len(opens) if covered else None,'source_consultation_seconds':seconds if exact else None,'consultation_seconds_diagnostic_estimate':seconds,'consultation_inferred_close':int(inferred),'source_consultation_complete':int(ended),'consultation_logging_coverage':a['logging_coverage'],'consultation_unclosed_intervals':len(set(opens)-set(closes)),'completed_exchanges':sum(x['status']=='completed' for x in xs),'discussion_sequence_completed':int(sum(x['status']=='completed' for x in xs)==5),**{k:measures.get(k) for k in s.MEASURES}}
                trust=[r[k] for k in ('trust_item_1','trust_item_2','trust_item_3')]; r['trust_mean']=sum(trust)/3 if all(v is not None for v in trust) else None
                out.append(r)
                result['measures'].extend({**base,**{k:a[k] for k in ('period','paper_id','condition','instrument_version','prompt_version','model_id')},**m} for m in s.rows(db,'SELECT * FROM v5_measures WHERE participant_id=? AND period=?',(pid,period)))
                result['consultation_events'].extend(ev)
                for x in xs:
                    provenance={k:r[k] for k in ('release_id','sequence_id','paper_id','condition','instrument_version','prompt_version','model_id')}
                    result['exchanges'].append({**x,**provenance})
                    result['requests'].extend({**q,**provenance,'participant_id':pid,'period':period} for q in s.rows(db,'SELECT * FROM v5_requests WHERE exchange_id=?',(x['exchange_id'],)))
                result['stage_attempts'].extend({**base,'paper_id':a['paper_id'],'condition':a['condition'],**pa} for pa in s.stage_attempts(pid,period,db))
                result['scaffold_events'].extend({**base,'condition':a['condition'],**e} for e in s.scaffold_events(pid,period,db))
            complete=int(all(r['actual_score'] is not None for r in out))
            for r in out: r['complete_pair']=complete
            result['periods'].extend(out);result['period1'].append(out[0])
            roster={**base,'complete_pair':complete,'session_completed':int(p['status']=='completed'),'stage':p['stage'],'completed_at':p['completed_at'],'deadline':p['deadline'],'final_json':p['final_json']}
            for r in out:
                for k in ('score','condition','paper'): roster[f"period{r['period']}_{k}"]=r[{'score':'actual_score','paper':'paper_id'}.get(k,k)]
            result['roster'].append(roster)
            result['transitions'].extend({**base,**e} for e in s.rows(db,'SELECT * FROM v5_transitions WHERE participant_id=?',(pid,)))
            orders=json.loads(p['option_order_json'])
            for period in (None,1,2):
                data={r['item_id']:r for r in s.rows(db,'SELECT * FROM v5_responses WHERE participant_id=?',(pid,))}
                for item in s.items(pid,period,db):
                    a=out[period-1] if period else {'period':None,'paper_id':'baseline','condition':None,'instrument_version':s.spec.INSTRUMENT_VERSION,'prompt_version':None,'model_id':None}
                    q={**base,**{k:a[k] for k in ('period','paper_id','condition','instrument_version','prompt_version','model_id')},'item_id':item['item_id'],'category':item['question_category'],'selected_option_id':data.get(item['item_id'],{}).get('selected_option_id'),'correct':data.get(item['item_id'],{}).get('correct'),'option_order_json':s.dumps(orders[item['item_id']]),'stage_elapsed_seconds':data.get(item['item_id'],{}).get('stage_elapsed_seconds'),'complete_pair':complete}
                    result['items'].append(q)
                    result['display_patterns'].append({**base,'item_id':item['item_id'],'key_display_position':orders[item['item_id']].index(item['correct_option_id'])+1})
        for paper,items in [('baseline',s.spec.BASELINE_ITEMS)]+[(k,v['mcqs']) for k,v in s.spec.PAPERS.items()]:
            for item in items:
                rs=[r for r in result['items'] if r['is_pilot'] and not r['is_test'] and r['item_id']==item['item_id']]; answered=[r for r in rs if r['correct'] is not None]
                result['pilot_items'].append({'item_id':item['item_id'],'paper_id':paper,'eligible_N':len(rs),'answered_N':len(answered),'missing_N':len(rs)-len(answered),'proportion_correct_answered':sum(r['correct'] for r in answered)/len(answered) if answered else None,'interpretation':'small-sample descriptive; not validation',**{opt:sum(r['selected_option_id']==opt for r in answered) for opt in item['option_ids']}})
    return result

def csv_bytes(rs):
    fields=list(dict.fromkeys(k for r in rs for k in r))
    out=io.StringIO();writer=csv.DictWriter(out,fields);writer.writeheader();writer.writerows(rs);return out.getvalue().encode()
def write_exports(path):
    from pathlib import Path
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,rs in export_data().items(): (path/(name+'.csv')).write_bytes(csv_bytes(rs))
    (path/'PRIVACY.txt').write_text('Restricted research export. Chat, learner text and final free text require review before public sharing. Names are stored separately and excluded here.\n')
