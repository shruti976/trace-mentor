#!/usr/bin/env python3
"""Freeze an immutable candidate. Pending human validation remains pending."""
import sys,json,hashlib,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import study_v5 as s
from v5_tutor import source
from datetime import datetime,timezone

def main():
    path=s.ROOT/'data/v5_manifest.json'
    if path.exists(): s.frozen_manifest(); print('Existing frozen version verified'); return
    from scripts.validate_v5_items import report
    findings=report()
    if any(f['severity']=='error' for f in findings): raise ValueError('Item integrity errors prevent freezing')
    papers=json.loads((s.ROOT/'data/papers/v5/provenance.json').read_text())
    for key in papers: source(key)
    m={'release_id':s.RELEASE_ID,'instrument_version':s.INSTRUMENT_VERSION,'instrument_hash':s.digest(s.snapshot()),'frozen_at':datetime.now(timezone.utc).isoformat(),'prompt_version':s.PROMPT_VERSION,'prompt_source_sha256':hashlib.sha256((s.ROOT/'v5_tutor.py').read_bytes()).hexdigest(),'rubric_source_sha256':hashlib.sha256((s.ROOT/'data/mentor_rubric.py').read_bytes()).hexdigest(),'generation_settings':s.GENERATION,'consent_sha256':s.CONSENT_SHA256,'papers':papers,'human_expert_review':'pending','excluded_pilot':'not_run','item_status':'frozen','automated_quality_findings':len(findings)}
    path.write_text(json.dumps(m,indent=2)+'\n'); print(json.dumps(m,indent=2))
if __name__=='__main__': main()
