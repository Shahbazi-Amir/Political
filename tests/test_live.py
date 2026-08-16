from __future__ import annotations
import os,pytest
pytestmark=pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS")!="1",reason="live tests are opt-in")
def test_live_pipeline_citation_integrity():
    from political_core.cli import _engine
    assert os.getenv("SEARXNG_URL") and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")
    result=_engine().check("اصل ۱۷۶ قانون اساسی درباره نمایندگان رهبری چه می‌گوید؟",mode="quick",refresh=True);available={e.evidence_id for e in result.evidence};assert set(result.citation_ids).issubset(available);assert result.cost_stats["reasoning_calls"]<=1
