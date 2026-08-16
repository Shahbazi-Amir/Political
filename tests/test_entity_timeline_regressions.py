from __future__ import annotations
from political_core.entity import extract_entities
from political_core.models import TimelineEvent
from political_core.timeline import active_role_events,derive_current_roles


def event(entity,role,event_type,date,entity_id,institution="شورای عالی امنیت ملی"):
    return TimelineEvent(entity,role,event_type,entity_id,institution,date)


def test_alias_does_not_match_inside_larger_latin_word():
    refs=extract_entities("Iranian officials issued a statement")
    assert not any(r.canonical_name=="ایران" for r in refs)


def test_alias_does_not_match_inside_larger_persian_word():
    refs=extract_entities("شهر ایرانشهر در استان سیستان و بلوچستان قرار دارد")
    assert not any(r.canonical_name=="ایران" for r in refs)


def test_alias_still_matches_as_standalone_token():
    refs=extract_entities("ایران و مجلس شورای اسلامی")
    assert any(r.canonical_name=="ایران" and r.entity_type=="country" for r in refs)
    assert any(r.canonical_name=="مجلس شورای اسلامی" for r in refs)


def test_ambiguous_replacement_does_not_close_all_multi_seat_roles():
    role="نماینده در شورای عالی امنیت ملی"
    a=event("الف",role,"appointment","2025-01-01","P1")
    b=event("ب",role,"appointment","2025-01-02","P2")
    replacement=event("ج",role,"replacement","2026-01-01","P3")
    roles=derive_current_roles([a,b,replacement])
    assert roles["P1"][0].end_date is None
    assert roles["P2"][0].end_date is None


def test_unique_replacement_can_close_unique_active_role():
    role="دبیر شورای عالی امنیت ملی"
    old=event("الف",role,"appointment","2025-01-01","P1")
    replacement=event("ب",role,"replacement","2026-01-01","P2")
    derive_current_roles([old,replacement])
    assert old.end_date=="2026-01-01"
