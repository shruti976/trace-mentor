"""Dispatch returning participants to their stored release implementation."""
import streamlit as st
import db_utils

def main():
    pid=st.query_params.get('participant_id') or st.query_params.get('session_id')
    if pid:
        from archive_utils import _table_exists
        db=db_utils.get_connection()
        try:
            new=_table_exists(db,'v5_participants') and db.execute(db_utils.db_query('SELECT participant_id FROM v5_participants WHERE participant_id=?'),(pid,)).fetchone()
            old=not new and _table_exists(db,'study_sessions_v2') and db.execute(db_utils.db_query('SELECT session_id FROM study_sessions_v2 WHERE session_id=?'),(pid,)).fetchone()
        finally:db.close()
        if old:
            from app_v4_crossover import main as legacy
            legacy();return
    from archive_utils import _table_exists
    db=db_utils.get_connection()
    try: ready=_table_exists(db,'v5_releases')
    finally: db.close()
    if not ready:
        st.info('The revised study is being prepared. Enrollment is closed. Please return later.');return
    from app_v5 import main as current
    current()
if __name__=='__main__':main()
