#!/usr/bin/env python3
"""Run unit discovery in a fresh process with a disposable database, before imports."""
import os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='humanai-safe-suite-') as directory:
    env=dict(os.environ)
    env.update(EXPERIMENT_DB_PATH=str(Path(directory)/'study.sqlite'),HUMAI_DATABASE_URL='',DATABASE_URL='',HUMAI_DEMO_MODE='true',HUMAI_RECRUITMENT_OPEN='true',HUMAI_IRB_AMENDMENT_APPROVED='true')
    raise SystemExit(subprocess.call([sys.executable,'-m','unittest','discover','-s','tests'],cwd=ROOT,env=env))
