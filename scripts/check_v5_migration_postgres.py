import sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.rows import dict_row
from unittest.mock import patch
import db_utils,archive_utils
from scripts import migrate_v4,migrate_v5
url='postgresql://localhost:6547/postgres';schema='automated_migration_'+uuid.uuid4().hex
root=psycopg.connect(url,autocommit=True);root.execute(f'CREATE SCHEMA {schema}')
def connection():return psycopg.connect(url,row_factory=dict_row,options=f'-c search_path={schema}')
try:
    with patch.object(db_utils,'DATABASE_URL',url),patch.object(db_utils,'get_connection',connection),patch.object(migrate_v4,'get_connection',connection),patch.object(archive_utils,'get_connection',connection):
        migrate_v5.main();migrate_v5.main()
        print('PASS PostgreSQL pre-migration backup verification, additive migration and repeat startup')
finally:root.execute(f'DROP SCHEMA {schema} CASCADE');root.close()
