from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
from .dataset import iter_jsonl
from .fetch import SafeHttpFetcher
from .source_snapshot import source_changed

def check_source_records(dataset_path:str|Path,*,fetcher=None,max_chars:int=200_000)->dict[str,Any]:
    fetcher=fetcher or SafeHttpFetcher();rows=[];checked=changed=missing=0
    for _,case in iter_jsonl(dataset_path):
        for record in case.get("ground_truth_source_records") or []:
            checked+=1;url=str(record.get("url") or "")
            try:
                text=fetcher.fetch_text(url,max_chars)
                is_changed=source_changed(record,text);changed+=int(is_changed)
                rows.append({"case_id":case.get("id"),"url":url,"status":"changed" if is_changed else "reachable"})
            except Exception as exc:
                missing+=1;rows.append({"case_id":case.get("id"),"url":url,"status":"missing","error":type(exc).__name__})
    return {"checked":checked,"changed":changed,"missing":missing,"results":rows}

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-dataset-sources");parser.add_argument("dataset");parser.add_argument("--output");args=parser.parse_args(argv);report=check_source_records(args.dataset);encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+"\n",encoding="utf-8")
    print(encoded);return 0
if __name__=="__main__":raise SystemExit(main())
