from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace

from .models import Evidence
from .text import token_set


def text_similarity(a: str, b: str) -> float:
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def assign_source_chains(evidence: Sequence[Evidence], similarity_threshold: float = 0.74) -> list[Evidence]:
    groups: list[list[int]] = []
    assigned: dict[int, int] = {}
    for i, item in enumerate(evidence):
        if i in assigned:
            continue
        group_index = len(groups)
        groups.append([i])
        assigned[i] = group_index
        for j in range(i + 1, len(evidence)):
            if j in assigned:
                continue
            other = evidence[j]
            same_explicit_source = bool(item.cited_source and other.cited_source and item.cited_source.casefold() == other.cited_source.casefold())
            highly_similar = text_similarity(f"{item.title} {item.excerpt[:1200]}", f"{other.title} {other.excerpt[:1200]}") >= similarity_threshold
            if same_explicit_source or highly_similar:
                groups[group_index].append(j)
                assigned[j] = group_index
    out = list(evidence)
    for indices in groups:
        seed = "|".join(sorted(evidence[i].canonical_url or evidence[i].url for i in indices))
        chain = "S" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
        for i in indices:
            out[i] = replace(out[i], source_chain_id=chain)
    return out


def independent_source_count(evidence: Sequence[Evidence]) -> int:
    items = list(evidence)
    if not items:
        return 0
    parent = list(range(len(items)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            same_domain = items[i].independence_key == items[j].independence_key
            same_chain = bool(items[i].source_chain_id and items[i].source_chain_id == items[j].source_chain_id)
            if same_domain or same_chain:
                union(i, j)
    return len({find(i) for i in range(len(items))})
