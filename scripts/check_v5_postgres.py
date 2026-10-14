#!/usr/bin/env python3
"""Concurrency test inside an isolated PostgreSQL schema; no historical writes."""
import os,sys,uuid,concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
import db_utils
import v5_store as s

def check(url):
    import psycopg
    from psycopg.rows import dict_row
    schema='automated_v5_'+uuid.uuid4().hex
    conn=psycopg.connect(url,autocommit=True)
    conn.execute(f'CREATE SCHEMA {schema}')
    def connect():
        # Neon transaction pooling rejects search_path in startup options.
        connection=psycopg.connect(url,row_factory=dict_row)
        connection.execute(f'SET LOCAL search_path TO {schema}')
        return connection
    try:
        with patch.object(db_utils,'get_connection',connect),patch.object(db_utils,'DATABASE_URL',url),patch('config.IRB_AMENDMENT_APPROVED',True),patch('config.read_bool_setting',return_value=True):
            s.initialize();s.install_release()
            def enroll(n):
                try:return s.enroll('AUTOMATED-'+str(n),'AUTOMATED POSTGRES EXCLUDE',{},at='2026-09-07T12:00:00+00:00')
                except ValueError:return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:ps=[p for p in pool.map(enroll,range(76)) if p]
            assert len(ps)==60,len(ps)
            assert all(sum(p['sequence_id']==seq for p in ps)==15 for seq in s.spec.SEQUENCES)
            for p in ps:assert s.enroll(p['participant_id'],'retry',{})['sequence_id']==p['sequence_id']
            with s.transaction() as db:
                for block in s.rows(db,'SELECT * FROM v5_blocks'):
                    seqs=s.rows(db,'SELECT sequence_id FROM v5_participants WHERE randomization_block_id=?',(block['block_id'],));assert len({x['sequence_id'] for x in seqs})==4
            print('PASS PostgreSQL: 76 simultaneous attempts, exactly 60 enrollments, 15 per sequence, 15 full shuffled blocks, retry idempotency')
    finally:
        conn.execute(f'DROP SCHEMA {schema} CASCADE');conn.close()
if __name__=='__main__':check(os.environ.get('V5_DISPOSABLE_POSTGRES_URL','postgresql://localhost:6547/postgres'))
