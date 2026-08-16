from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass,field,replace
from datetime import datetime

from .models import Evidence
from .text import normalize_text,token_set


def text_similarity(a:str,b:str)->float:
    aa,bb=token_set(a),token_set(b)
    if not aa or not bb:return 0.0
    return len(aa&bb)/len(aa|bb)


def _quote_overlap(a:str,b:str)->float:
    qa=set(re.findall(r'["«]([^"»]{12,180})["»]',a));qb=set(re.findall(r'["«]([^"»]{12,180})["»]',b))
    if not qa or not qb:return 0.0
    na={normalize_text(x).casefold() for x in qa};nb={normalize_text(x).casefold() for x in qb}
    return len(na&nb)/max(1,len(na|nb))


def _word_sequence(text:str)->list[str]:return [x for x in re.findall(r"[\w\u0600-\u06ff]+",normalize_text(text).casefold()) if len(x)>1]
def _shingles(text:str,size:int=5)->set[tuple[str,...]]:
    words=_word_sequence(text)
    if len(words)<size:return set()
    return {tuple(words[i:i+size]) for i in range(len(words)-size+1)}
def shingle_containment(a:str,b:str,size:int=5)->float:
    aa,bb=_shingles(a,size),_shingles(b,size)
    if not aa or not bb:return 0.0
    return len(aa&bb)/max(1,min(len(aa),len(bb)))
def _paragraphs(text:str)->list[str]:
    parts=[normalize_text(x) for x in re.split(r"\n+|(?<=[.!?؟])\s+",text) if normalize_text(x)]
    return [x for x in parts if len(_word_sequence(x))>=10][:60]
def paragraph_overlap(a:str,b:str)->float:
    pa,pb=_paragraphs(a),_paragraphs(b)
    if not pa or not pb:return 0.0
    matched=0;used=set()
    for left in pa:
        best_j=None;best=0.0
        for j,right in enumerate(pb):
            if j in used:continue
            sim=text_similarity(left,right)
            if sim>best:best_j=j;best=sim
        if best_j is not None and best>=.82:used.add(best_j);matched+=1
    return matched/max(1,min(len(pa),len(pb)))
def _time_distance_hours(a:str|None,b:str|None)->float|None:
    if not a or not b:return None
    try:
        aa=datetime.fromisoformat(a.replace("Z","+00:00"));bb=datetime.fromisoformat(b.replace("Z","+00:00"));return abs((aa-bb).total_seconds())/3600
    except Exception:return None

def _source_key(value:str)->str:
    value=normalize_text(value).casefold();value=re.sub(r"(خبرگزاری|news\s*agency|agency|news|press|شبکه|پایگاه)"," ",value);value=re.sub(r"[^\w\u0600-\u06ff]+"," ",value);return "".join(value.split())
def _source_names(e:Evidence)->set[str]:
    values={e.domain.split(".")[0],e.publisher or "",e.cited_source or ""};return {_source_key(x) for x in values if _source_key(x)}
def _explicit_attributions(text:str)->set[str]:
    patterns=(r"(?:به نقل از|به گزارش)\s+([^،,:؛\n]{2,70})",r"(?:according to|reported by|via)\s+([A-Za-z0-9 ._-]{2,70})");out=set()
    for pat in patterns:
        for match in re.findall(pat,text,flags=re.I):
            key=_source_key(match)
            if key:out.add(key)
    return out


@dataclass(slots=True)
class ProvenanceEdge:
    source_index:int;target_index:int;relation:str;confidence:float;reason:str
@dataclass(slots=True)
class ProvenanceGraph:
    edges:list[ProvenanceEdge]=field(default_factory=list)
    def add(self,a:int,b:int,relation:str,confidence:float,reason:str)->None:self.edges.append(ProvenanceEdge(a,b,relation,round(confidence,3),reason))


def build_source_graph(evidence:Sequence[Evidence],similarity_threshold:float=.74)->ProvenanceGraph:
    graph=ProvenanceGraph();strong_threshold=max(.86,min(.95,similarity_threshold+.12))
    for i in range(len(evidence)):
        for j in range(i+1,len(evidence)):
            a,b=evidence[i],evidence[j];ac=_source_key(a.cited_source or "");bc=_source_key(b.cited_source or "")
            if ac and bc and ac==bc:graph.add(i,j,"same_explicit_source",.99,"same cited_source");continue
            a_names,b_names=_source_names(a),_source_names(b);a_attr=_explicit_attributions(f"{a.title}\n{a.excerpt[:2500]}");b_attr=_explicit_attributions(f"{b.title}\n{b.excerpt[:2500]}")
            if (a_attr&b_names) or (b_attr&a_names) or (ac and ac in b_names) or (bc and bc in a_names):graph.add(i,j,"cites_other_source",.97,"explicit attribution matches other publisher/domain");continue
            sample_a=f"{a.title}\n{a.excerpt[:2600]}";sample_b=f"{b.title}\n{b.excerpt[:2600]}";sim=text_similarity(sample_a,sample_b);qo=_quote_overlap(a.excerpt[:2500],b.excerpt[:2500]);para=paragraph_overlap(a.excerpt[:3500],b.excerpt[:3500]);shingle=shingle_containment(a.excerpt[:3500],b.excerpt[:3500]);hours=_time_distance_hours(a.published_at,b.published_at)
            if para>=.5 or shingle>=.72:
                conf=.94 if hours is None or hours<=72 else .86;graph.add(i,j,"near_verbatim_reproduction",conf,f"paragraph_overlap={para:.2f},shingle_containment={shingle:.2f}");continue
            if sim>=strong_threshold:
                conf=.92 if hours is None or hours<=48 else .82;graph.add(i,j,"likely_copy_or_syndication",conf,f"text_similarity={sim:.2f}");continue
            if sim>=similarity_threshold and (qo>=.5 or shingle>=.4):graph.add(i,j,"likely_shared_source",.79,f"text_similarity={sim:.2f},quote_overlap={qo:.2f},shingle={shingle:.2f}");continue
            if qo>=.8 and hours is not None and hours<=24:graph.add(i,j,"likely_shared_source",.72,f"quote_overlap={qo:.2f},hours={hours:.1f}")
    return graph


def assign_source_chains(evidence:Sequence[Evidence],similarity_threshold:float=.74,chain_threshold:float=.82)->list[Evidence]:
    """Assign only sufficiently strong provenance links to copy chains.

    We keep weaker 0.7–0.81 graph edges as diagnostic hypotheses, but do not let them
    transitively collapse otherwise independent publishers via single-linkage chaining.
    """
    items=list(evidence);graph=build_source_graph(items,similarity_threshold);threshold=max(.7,min(.99,float(chain_threshold)));parent=list(range(len(items)));edge_reason={};edge_conf={}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra!=rb:parent[rb]=ra
    for edge in graph.edges:
        if edge.confidence>=threshold:
            union(edge.source_index,edge.target_index);edge_reason[(edge.source_index,edge.target_index)]=edge.reason;edge_conf[(edge.source_index,edge.target_index)]=edge.confidence
    groups={}
    for i in range(len(items)):groups.setdefault(find(i),[]).append(i)
    out=list(items)
    for indices in groups.values():
        seed="|".join(sorted(items[i].canonical_url or items[i].url for i in indices));chain="S"+hashlib.sha1(seed.encode()).hexdigest()[:10];group_conf=0.0;reasons=[]
        for a in indices:
            for b in indices:
                if a<b:
                    c=edge_conf.get((a,b),edge_conf.get((b,a),0))
                    if c:group_conf=max(group_conf,c);reasons.append(edge_reason.get((a,b),edge_reason.get((b,a),"")))
        for i in indices:
            if len(indices)>1:out[i]=replace(out[i],source_chain_id=chain,source_chain_confidence=round(group_conf or threshold,3),source_chain_reason="; ".join(dict.fromkeys(x for x in reasons if x))[:300])
            else:out[i]=replace(out[i],source_chain_id=chain,source_chain_confidence=0.0,source_chain_reason="singleton")
    return out


@dataclass(slots=True)
class IndependenceAssessment:
    certain_independent:int=0;likely_independent:int=0;likely_same_chain:int=0;certain_same_chain:int=0
    @property
    def conservative_count(self)->int:return self.certain_independent+self.likely_independent

def assess_independence(evidence:Sequence[Evidence])->IndependenceAssessment:
    items=list(evidence)
    if not items:return IndependenceAssessment()
    groups={}
    for e in items:
        key=("chain",e.source_chain_id) if e.source_chain_id and e.source_chain_confidence>=.82 else ("domain",e.independence_key);groups.setdefault(key,[]).append(e)
    certain_same=sum(max(0,len(v)-1) for v in groups.values() if any(x.source_chain_confidence>=.9 for x in v));likely_same=sum(max(0,len(v)-1) for v in groups.values() if len(v)>1 and not any(x.source_chain_confidence>=.9 for x in v));certain=sum(1 for v in groups.values() if len(v)==1 and v[0].source_chain_confidence==0);likely=max(0,len(groups)-certain)
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
            same_domain=items[i].independence_key==items[j].independence_key;same_chain=bool(items[i].source_chain_id and items[i].source_chain_id==items[j].source_chain_id and min(items[i].source_chain_confidence,items[j].source_chain_confidence)>=.82)
            if same_domain or same_chain:union(i,j)
    return len({find(i) for i in range(len(items))})
