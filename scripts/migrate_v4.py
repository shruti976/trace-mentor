#!/usr/bin/env python3
"""Verify a persistent pre-migration backup, then add crossover columns."""
from pathlib import Path
import sys, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from db_utils import get_connection,db_placeholder,using_postgres
from archive_utils import build_archive_bytes,verify_archive_bytes
from data.crossover import RELEASE_ID

def stored_backup():
    db = get_connection()
    try:
        from archive_utils import _table_exists
        if not _table_exists(db, "study_release_backups"):
            return None
        row = db.execute("SELECT archive_data, sha256, manifest_token FROM study_release_backups WHERE release_id = " + db_placeholder(), (RELEASE_ID,)).fetchone()
        if not row:
            return None
        payload = bytes(row["archive_data"])
        if hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise RuntimeError("Backup checksum mismatch")
        verify_archive_bytes(payload, expected_token=row["manifest_token"])
        return payload
    finally:
        db.close()

def main():
    db=get_connection()
    try:
        with (db.transaction() if using_postgres() else db):
            db.execute('CREATE TABLE IF NOT EXISTS study_release_backups (release_id TEXT PRIMARY KEY, archive_data '+('BYTEA' if using_postgres() else 'BLOB')+', sha256 TEXT NOT NULL, manifest_token TEXT NOT NULL, created_at TEXT NOT NULL)')
            row=db.execute('SELECT archive_data, sha256, manifest_token FROM study_release_backups WHERE release_id = '+db_placeholder(),(RELEASE_ID,)).fetchone()
        if row:
            payload=bytes(row['archive_data']); token=row['manifest_token']
            if hashlib.sha256(payload).hexdigest()!=row['sha256']: raise RuntimeError('Stored backup checksum mismatch')
            verify_archive_bytes(payload,expected_token=token)
        else:
            from datetime import datetime,timezone
            payload,manifest,token=build_archive_bytes()
            with (db.transaction() if using_postgres() else db):
                db.execute('INSERT INTO study_release_backups (release_id,archive_data,sha256,manifest_token,created_at) VALUES ('+', '.join(db_placeholder() for _ in range(5))+') ON CONFLICT (release_id) DO NOTHING',(RELEASE_ID,payload,hashlib.sha256(payload).hexdigest(),token,datetime.now(timezone.utc).isoformat()))
                stored=db.execute('SELECT archive_data, manifest_token FROM study_release_backups WHERE release_id = '+db_placeholder(),(RELEASE_ID,)).fetchone()
                verify_archive_bytes(bytes(stored['archive_data']),expected_token=stored['manifest_token'])
        print('Verified persistent pre-migration backup: '+RELEASE_ID+'; bytes='+str(len(payload)))
    finally: db.close()
    from v4_utils import connection,initialize_v4_database
    initialize_v4_database()
    with connection() as db:
        rows=db.execute('SELECT COALESCE(study_version,experiment_version) AS version, COUNT(*) AS n FROM study_sessions_v2 GROUP BY COALESCE(study_version,experiment_version)').fetchall()
    print('Additive migration complete; preserved version counts: '+', '.join(f"{r['version']}={r['n']}" for r in rows))
    return 0
if __name__=='__main__': raise SystemExit(main())
