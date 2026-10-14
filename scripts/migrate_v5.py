#!/usr/bin/env python3
"""Verify a restricted pre-migration archive, then install additive V5 schema."""
import sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data.study_v5 import RELEASE_ID
from scripts import migrate_v4

def main():
    # Reuse audited backup mechanism under a distinct backup release key.
    migrate_v4.RELEASE_ID=RELEASE_ID
    migrate_v4.main()
    if not migrate_v4.stored_backup():raise RuntimeError('Verified backup is required')
    import v5_store as s
    s.initialize();s.install_release()
    print('V5 additive schema and immutable release installed; historical tables retained')
if __name__=='__main__':main()
