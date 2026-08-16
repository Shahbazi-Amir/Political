from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from .models import Evidence
from .text import normalize_text, token_set


def text_similarity(a:str,b:str)->float:
    aa,bb=token_set(a),token_set(b)
    if not aa or not bb:return 0.0
    return len(aa&bb)/len(aa|bb)


def _quote_overlap(a:str,b:str)->float:
    qa=set(re.findall(r'["«]([^"»]{12,180})["»]',a));qb=set(re.findall(r'["«]([^"»]{12,180})["»]',b))
    if not qa or not qb:return 0.0
    na={normalize_text(x).casefold() for x in qa};nb={normalize_text(x).casefold() for x in qb}
    return len(na&nb)/max(1,len(na|nb))


def _time_distance_hours(a:str|None,b:str|None)->float|None:
    if not a or not b:return None
    try:
        aa=datetime.fromisoformat(a.replace("Z","+00:00"));bb=datetime.fromisoformat(b.replace("Z","+00:00"))
        return abs((aa-bb).total_seconds())/3600
    except Exception:return None


def _source_names(e:Evidence)->set[str]:
    values={e.domain.split(".")[0],e.publisher or "",e.cited_source or ""}
    return {normalize_text(x).casefold().replace(" ","") for x in values if x}


@dataclass(slots=True)
class ProvenanceEdge:
    source_index:int
    target_index:int
    relation:str
    confidence:float
    reason:str


@dataclass(slots=True)
class ProvenanceGraph:
    edges:list[ProvenanceEdge]=field(default_factory=list)
    def add(self,a:int,b:int,relation:str,confidence:float,reason:str)->None:
        self.edges.append(ProvenanceEdge(a,b,relation,round(confidence,3),reason))


def build_source_graph(evidence:Sequence[Evidence],similarity_threshold:float=.74)->ProvenanceGraph:
    graph=ProvenanceGraph();strong_threshold=max(.86,min(.95,similarity_threshold+.12))
    for i in range(len(evidence)):
        for j in range(i+1,len(evidence)):
            a,b=evidence[i],evidence[j]
            ac=normalize_text(a.cited_source or "").casefold().replace(" ","")
            bc=normalize_text(b.cited_source or "").casefold().replace(" ","")
            if ac and bc and ac==bc:
                graph.add(i,j,"same_explicit_source",.99,"same cited_source");continue
            # Link a downstream attribution to the original outlet itself when possible.
            if (ac and ac in _source_names(b)) or (bc and bc in _source_names(a)):
                graph.add(i,j,"cites_other_source",.96,"explicit attribution matches other publisher/domain");continue
            sim=text_similarity(f"{a.title} {a.excerpt[:1800]}",f"{b.title} {b.excerpt[:1800]}")
            qo=_quote_overlap(a.excerpt[:2500],b.excerpt[:2500]);hours=_time_distance_hours(a.published_at,b.published_at)
            if sim>=strong_threshold:
                conf=.92 if hours is None or hours<=48 else .82
                graph.add(i,j,"likely_copy_or_syndication",conf,f"text_similarity={sim:.2f}")
            elif sim>=similarity_threshold and qo>=.5:
                graph.add(i,j,"likely_shared_source",.78,f"text_similarity={sim:.2f},quote_overlap={qo:.2f}")
            elif qo>=.8 and hours is not None and hours<=24:
                graph.add(i,j,"likely_shared_source",.72,f"quote_overlap={qo:.2f},hours={hours:.1f}")
    return graph


def assign_source_chains(evidence:Sequence[Evidence],similarity_threshold:float=.74)->list[Evidence]:
    items=list(evidence);graph=build_source_graph(items,similarity_threshold);parent=list(range(len(items)));edge_reason={};edge_conf={}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb:parent[rb]=ra
    for edge in graph.edges:
        if edge.confidence>=.7:
            union(edge.source_index,edge.target_index);edge_reason[(edge.source_index,edge.target_index)]=edge.reason;edge_conf[(edge.source_index,edge.target_index)]=edge.confidence
    groups={}
    for i in range(len(items)):groups.setdefault(find(i),[]).append(i)
    out=list(items)
    for indices in groups.values():
        seed="|".join(sorted(items[i].canonical_url or items[i].url for i in indices));chain="S"+hashlib.sha1(seed.encode()).hexdigest()[:10]
        group_conf=0.0;reasons=[]
        for a in indices:
            for b in indices:
                if a<b:
                    c=edge_conf.get((a,b),edge_conf.get((b,a),0))
                    if c:group_conf=max(group_conf,c);reasons.append(edge_reason.get((a,b),edge_reason.get((b,a),"")))
        for i in indices:
            if len(indices)>1:
                out[i]=replace(out[i],source_chain_id=chain,source_chain_confidence=round(group_conf or .7,3),source_chain_reason="; ".join(dict.fromkeys(x for x in reasons if x))[:240])
            else:out[i]=replace(out[i],source_chain_id=chain,source_chain_confidence=0.0,source_chain_reason="singleton")
    return out


@dataclass(slots=True)
class IndependenceAssessment:
    certain_independent:int=0
    likely_independent:int=0
    likely_same_chain:int=0
    certain_same_chain:int=0
    @property
    def conservative_count(self)->int:return self.certain_independent+self.likely_independent


def assess_independence(evidence:Sequence[Evidence])->IndependenceAssessment:
    items=list(evidence)
    if not items:return IndependenceAssessment()
    groups={}
    for e in items:
        # A high-confidence source-chain groups cross-domain copies together.
        key=("chain",e.source_chain_id) if e.source_chain_id and e.source_chain_confidence>=.7 else ("domain",e.independence_key)
        groups.setdefault(key,[]).append(e)
    certain_same=sum(max(0,len(v)-1) for v in groups.values() if any(x.source_chain_confidence>=.9 for x in v))
    likely_same=sum(max(0,len(v)-1) for v in groups.values() if len(v)>1 and not any(x.source_chain_confidence>=.9 for x in v))
    certain=sum(1 for v in groups.values() if len(v)==1 and v[0].source_chain_confidence==0)
    likely=max(0,len(groups)-certain)
    return IndependenceAssessment(certain,likely,likely_same,certain_same)


def independent_source_count(evidence:Sequence[Evidence])->int:
    items=list(evidence)
    if not items:return 0
    parent=list(range(len(items)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb:parent[rb]=ra
    for i in range(len(items)):
        for j in range(i+1,len(items)):
            same_domain=items[i].independence_key==items[j].independence_key
            same_chain=bool(items[i].source_chain_id and items[i].source_chain_id==items[j].source_chain_id and min(items[i].source_chain_confidence,items[j].source_chain_confidence)>=.7)
            if same_domain or same_chain:union(i,j)
    return len({find(i) for i in range(len(items))})
