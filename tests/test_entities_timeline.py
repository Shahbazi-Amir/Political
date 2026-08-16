from __future__ import annotations
from political_core.claims import analyze_claims
from political_core.entity import EntityAliasRegistry,extract_entities
from political_core.models import Evidence,SourceKind,SourceRole
from political_core.timeline import build_timeline
def test_shaaam_alias_normalizes():assert EntityAliasRegistry().canonicalize("شعام")=="شورای عالی امنیت ملی"
def test_person_without_title_can_be_extracted_near_role():assert any(r.entity_type=="person" and "ذوالقدر" in r.canonical_name for r in extract_entities("محمدباقر ذوالقدر دبیر شورای عالی امنیت ملی شد"))
def test_claim_has_entity_refs():assert analyze_claims("محمدباقر ذوالقدر دبیر شورای عالی امنیت ملی شد")[0].entity_refs
def test_timeline_keeps_role_and_entity():
    claims=analyze_claims("محمدباقر ذوالقدر دبیر شورای عالی امنیت ملی شد");e=Evidence("E1","https://a.example/x","حکم انتصاب محمدباقر ذوالقدر دبیر شورای عالی امنیت ملی","a.example","محمدباقر ذوالقدر منصوب شد به عنوان دبیر شورای عالی امنیت ملی","2026-03-24T00:00:00+00:00",SourceKind.NEWSROOM,.8,"a.example",source_role=SourceRole.SECONDARY_REPORTING);events=build_timeline(claims,[e]);assert events;assert "دبیر" in events[0].role;assert events[0].event_type=="appointment"
