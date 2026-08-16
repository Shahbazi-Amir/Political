from __future__ import annotations

import os
import pytest

pytestmark=pytest.mark.live


def _configured()->bool:
    return bool(os.getenv("RUN_LIVE_TESTS")=="1" and os.getenv("SEARXNG_URL") and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


@pytest.mark.skipif(not _configured(),reason="live tests require RUN_LIVE_TESTS=1, SearxNG and OpenAI credentials")
def test_live_quick_pipeline_integrity():
    from political_core.cli import _engine
    result=_engine().check("اصل ۱۷۶ قانون اساسی درباره دو نماینده رهبری در شورای عالی امنیت ملی چه می‌گوید؟",mode="quick",refresh=True)
    available={e.evidence_id for e in result.evidence}
    assert set(result.citation_ids).issubset(available)
    assert result.cost_stats["reasoning_calls"]<=1
    assert result.cost_stats["search_queries"]<=2
    assert result.verdict.value in {"true","mostly_true","missing_context","misleading","mostly_false","false","unverified","insufficient_evidence","conflicting_evidence","outdated","opinion_not_fact","prediction","verification_unavailable"}


@pytest.mark.skipif(not _configured(),reason="live tests require RUN_LIVE_TESTS=1, SearxNG and OpenAI credentials")
def test_live_deep_pipeline_judge_critic_integrity():
    from political_core.cli import _engine
    result=_engine().check("بررسی کن آیا دبیر شورای عالی امنیت ملی صرفاً به دلیل دبیر بودن، خودکار یکی از دو نماینده رهبری هم محسوب می‌شود.",mode="deep",refresh=True)
    available={e.evidence_id for e in result.evidence}
    assert set(result.citation_ids).issubset(available)
    assert result.cost_stats["reasoning_calls"]<=2
    assert result.cost_stats["search_queries"]<=6
