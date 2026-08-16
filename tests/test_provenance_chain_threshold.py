from __future__ import annotations
from unittest.mock import patch
from political_core.models import Evidence,SourceKind,SourceRole
from political_core.provenance import ProvenanceEdge,ProvenanceGraph,assign_source_chains,independent_source_count


def ev(i,domain):
    return Evidence(f"E{i}",f"https://{domain}/{i}",f"title {i}",domain,"text evidence",None,SourceKind.NEWSROOM,.7,domain,source_role=SourceRole.SECONDARY_REPORTING)


def test_weak_provenance_hypothesis_does_not_collapse_independent_sources():
    graph=ProvenanceGraph([ProvenanceEdge(0,1,"likely_shared_source",.79,"weak semantic/quote overlap")])
    with patch("political_core.provenance.build_source_graph",return_value=graph):
        rows=assign_source_chains([ev(1,"a.example"),ev(2,"b.example")])
    assert rows[0].source_chain_id!=rows[1].source_chain_id
    assert independent_source_count(rows)==2


def test_strong_provenance_edge_still_collapses_copy_chain():
    graph=ProvenanceGraph([ProvenanceEdge(0,1,"likely_copy_or_syndication",.92,"near copy")])
    with patch("political_core.provenance.build_source_graph",return_value=graph):
        rows=assign_source_chains([ev(1,"a.example"),ev(2,"b.example")])
    assert rows[0].source_chain_id==rows[1].source_chain_id
    assert rows[0].source_chain_confidence==.92
    assert independent_source_count(rows)==1


def test_chain_threshold_can_be_made_stricter_for_forensic_runs():
    graph=ProvenanceGraph([ProvenanceEdge(0,1,"likely_copy_or_syndication",.90,"copy signal")])
    with patch("political_core.provenance.build_source_graph",return_value=graph):
        rows=assign_source_chains([ev(1,"a.example"),ev(2,"b.example")],chain_threshold=.95)
    assert independent_source_count(rows)==2
