from __future__ import annotations
import argparse,gzip,hashlib,json
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from .dataset import REQUIRED_CATEGORIES,iter_jsonl,validate_jsonl

@dataclass(frozen=True,slots=True)
class DatasetManifest:
    schema_version:int
    dataset_version:str
    file_sha256:str
    canonical_content_sha256:str
    file_name:str
    total_cases:int
    auditable_verified_cases:int
    category_counts:dict[str,int]
    generated_at:str
    split_policy_version:str="split-v1"
    @property
    def sha256(self)->str:
        """Compatibility alias for the semantic dataset identity."""
        return self.canonical_content_sha256
    def to_dict(self)->dict[str,Any]:
        out=asdict(self);out["sha256"]=self.canonical_content_sha256;return out

def file_sha256(path:str|Path)->str:
    digest=hashlib.sha256()
    with open(path,"rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()

def canonical_content_sha256(path:str|Path)->str:
    rows=[]
    for _,row in iter_jsonl(path):
        if "__parse_error__" in row:raise ValueError("dataset parse error")
        rows.append(row)
    rows.sort(key=lambda x:str(x.get("id") or ""))
    digest=hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()

def build_dataset_manifest(path:str|Path,*,dataset_version:str|None=None,required_reviewers:int=1,minimum_identity_assurance:str="unverified")->DatasetManifest:
    path=Path(path);file_digest=file_sha256(path);semantic=canonical_content_sha256(path);validation=validate_jsonl(path,required_reviewers=required_reviewers,minimum_identity_assurance=minimum_identity_assurance)
    if not validation.valid:raise ValueError("dataset is invalid and cannot be versioned")
    return DatasetManifest(2,dataset_version or f"ds-{semantic[:12]}",file_digest,semantic,path.name,validation.total_cases,validation.auditable_verified_cases,{key:validation.category_counts.get(key,0) for key in REQUIRED_CATEGORIES},datetime.now(timezone.utc).isoformat())

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="political-dataset-manifest");parser.add_argument("dataset");parser.add_argument("--version");parser.add_argument("--required-reviewers",type=int,default=1);parser.add_argument("--minimum-identity-assurance",default="unverified",choices=["unverified","registry_verified","externally_authenticated"]);parser.add_argument("--output");args=parser.parse_args(argv)
    manifest=build_dataset_manifest(args.dataset,dataset_version=args.version,required_reviewers=args.required_reviewers,minimum_identity_assurance=args.minimum_identity_assurance);encoded=json.dumps(manifest.to_dict(),ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+"\n",encoding="utf-8")
    print(encoded);return 0
if __name__=="__main__":raise SystemExit(main())
