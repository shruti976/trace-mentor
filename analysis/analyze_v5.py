#!/usr/bin/env python3
"""One command: export stored V5 data and run the locked manuscript models."""
import argparse,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exports',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--export-db',action='store_true');args=parser.parse_args()
    if args.export_db:
        from v5_exports import write_exports
        write_exports(args.exports)
    return subprocess.call(['Rscript',str(ROOT/'analysis/analyze_v5.R'),str(args.exports.resolve()),str(args.output.resolve())])
if __name__=='__main__':raise SystemExit(main())
