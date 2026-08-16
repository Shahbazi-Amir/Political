from __future__ import annotations
import argparse, hashlib, json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .dataset import REQUIRED_CATEGORIES, validate_jsonl

@dataclass(frozen=True, slots=True)
class DatasetManifest:
    schema_version:int
    dataset_version:str
    sha256:str
    file_name:str
    total_cases:int
    auditable_verified_cases:int
    category_counts:dict[str,int]
    generated_at:str
    def to_dict(self)->dict[str,Any]: return asdict(self)

def file_sha256(path:str|Path)->str:
    digest=hashlib.sha256()
    with open(path,"rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()

def build_dataset_manifest(path:str|Path,*,dataset_version:str|None=None)->DatasetManifest:
    path=Path(path); digest=file_sha256(path); validation=validate_jsonl(path)
    if not validation.valid: raise ValueError("dataset is invalid and cannot be versioned")
    return DatasetManifest(1,dataset_version or f"ds-{digest[:12]}",digest,path.name,validation.total_cases,validation.auditable_verified_cases,{key:validation.category_counts.get(key,0) for key in REQUIRED_CATEGORIES},datetime.now(timezone.utc).isoformat())

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-dataset-manifest");parser.add_argument("dataset");parser.add_argument("--version");parser.add_argument("--output");args=parser.parse_args(argv)
    manifest=build_dataset_manifest(args.dataset,dataset_version=args.version);encoded=json.dumps(manifest.to_dict(),ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+"\n",encoding="utf-8")
    print(encoded);return 0
if __name__=="__main__":raise SystemExit(main())
