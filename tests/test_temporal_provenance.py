from __future__ import annotations
from datetime import datetime,timezone
from political_core.models import Evidence,SourceKind,SourceRole
from political_core.provenance import assign_source_chains,independent_source_count,text_similarity
from political_core.temporal import FreshnessPolicy,jalali_to_gregorian,parse_date_text
def ev(i,domain,text,cited=None,published=None):
    return Evidence(f"E{i}",f"https://{domain}/{i}",text,domain,text*3,published,SourceKind.NEWSROOM,.7,domain,canonical_url=f"https://{domain}/{i}",source_role=SourceRole.SECONDARY_REPORTING,cited_source=cited,relevance_score=.7)
def test_jalali_known_conversion():assert jalali_to_gregorian(1405,5,18)==(2026,8,9)
def test_parse_named_jalali_date():
    items=parse_date_text("در ۱۸ مرداد ۱۴۰۵ حکم صادر شد",datetime(2026,8,16,tzinfo=timezone.utc));assert any(x.calendar=="jalali" and x.parsed_datetime.startswith("2026-08-09") for x in items)
def test_parse_slash_jalali_date():assert parse_date_text("1405/05/18",datetime(2026,8,16,tzinfo=timezone.utc))[0].parsed_datetime.startswith("2026-08-09")
def test_parse_relative_yesterday():
    ref=datetime(2026,8,16,12,tzinfo=timezone.utc);items=parse_date_text("این خبر دیروز منتشر شد",ref);assert any(x.parsed_datetime.startswith("2026-08-15") for x in items)
def test_current_office_freshness_is_short():
    from political_core.claims import analyze_claims
    claims=analyze_claims("الان دبیر شورا کیست؟",reference_date=datetime(2026,8,16,tzinfo=timezone.utc));policy=FreshnessPolicy(current_office_days=14);e=ev(1,"a.example","old","x","2026-07-01T00:00:00+00:00");assert policy.evidence_is_stale(e,claims,datetime(2026,8,16,tzinfo=timezone.utc))
def test_explicit_shared_wire_is_one_chain():
    items=assign_source_chains([ev(1,"a.example","گزارش اول درباره یک رویداد","wire-x"),ev(2,"b.example","بازنویسی متفاوت درباره همان رویداد","wire-x")]);assert items[0].source_chain_id==items[1].source_chain_id;assert items[0].source_chain_confidence>=.9;assert independent_source_count(items)==1
def test_highly_similar_cross_domain_copy_is_grouped():
    text="جزئیات رویداد سیاسی مشترک با جملات و عبارت های بسیار مشابه و اطلاعات یکسان";items=assign_source_chains([ev(1,"a.example",text),ev(2,"b.example",text)]);assert items[0].source_chain_id==items[1].source_chain_id;assert independent_source_count(items)==1
def test_different_reports_can_remain_independent():
    items=assign_source_chains([ev(1,"a.example","خبرنگار اول از محل رأی گیری و شمارش صندوق ها گزارش داد"),ev(2,"b.example","خبرنگار دوم مصاحبه مستقلی با یک مقام محلی انجام داد")]);assert independent_source_count(items)==2
def test_similarity_bounds():assert 0<=text_similarity("الف ب ج","متن متفاوت")<=1
