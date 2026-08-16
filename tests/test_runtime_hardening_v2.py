from __future__ import annotations
import pytest
from political_core.application import PoliticalApplication
from political_core.cache_backend import MemoryCache,RedisCache,ResilientCache
from political_core.cached_providers import CachedSearchProvider
from political_core.loadtest import run_load_test
from political_core.models import FactCheckResult,SearchResult,Verdict
from political_core.observability import MemoryMetricsSink,metric_from_result
from political_core.rate_limit import SlidingWindowRateLimiter
from political_core.telegram_adapter import TelegramAdapter

class FakeRedis:
    def __init__(self):self.rows={};self.ex={}
    def get(self,key):return self.rows.get(key)
    def set(self,key,value,ex=None):self.rows[key]=value;self.ex[key]=ex
    def delete(self,key):self.rows.pop(key,None)

def test_redis_uses_native_ttl():
    fake=FakeRedis();cache=RedisCache(client=fake)
    cache.set("x",{"v":1},30)
    assert fake.ex["political:x"]==30 and cache.get("x",30)=={"v":1}

class BrokenCache:
    def get(self,*a,**k):raise RuntimeError("down")
    def set(self,*a,**k):raise RuntimeError("down")
    def delete(self,*a,**k):raise RuntimeError("down")

def test_cache_fail_open():
    cache=ResilientCache(BrokenCache(),fail_open=True)
    assert cache.get("x",10) is None
    cache.set("x",{"v":1},10);cache.delete("x")
    assert len(cache.errors)==3

class Searcher:
    def __init__(self):self.calls=0
    def search(self,q,limit):
        self.calls+=1;return [SearchResult("https://example.org","title")]

def test_provider_stats_are_request_local_deltas():
    inner=Searcher();provider=CachedSearchProvider(inner,MemoryCache(),60)
    provider.search("x",2);first=provider.stats
    provider.search("x",2);second=provider.stats
    assert first["provider_calls"]==1 and first["cache_hits"]==0
    assert second["provider_calls"]==0 and second["cache_hits"]==1

def test_final_cache_metric_does_not_replay_historical_provider_calls():
    result=FactCheckResult("c","c",Verdict.TRUE,.8,"ok",[],"",[],[],from_cache=True,diagnostics={"search_provider_stats":{"provider_calls":9,"cache_hits":4}},analysis={"fetch_provider_stats":{"provider_calls":8,"cache_hits":3}})
    metric=metric_from_result(result,"r",mode="quick")
    assert metric.search_count==0 and metric.fetch_count==0 and metric.search_cache_hits==0 and metric.fetch_cache_hits==0

def test_rate_limiter_subject_memory_is_bounded():
    limiter=SlidingWindowRateLimiter(10,3600,max_subjects=100)
    for i in range(1000):assert limiter.allow(str(i),now=float(i))
    assert len(limiter)<=100

class CountingEngine:
    def check(self,claim,mode="quick",refresh=False,reference_date=None):
        return FactCheckResult(claim,claim,Verdict.UNVERIFIED,.2,"ok",[],"",[],[])
class BrokenEngine:
    def check(self,*a,**k):raise RuntimeError("provider exploded")

def test_telegram_last_result_store_is_bounded():
    adapter=TelegramAdapter(PoliticalApplication(CountingEngine()),last_result_max_users=3,last_result_ttl_seconds=3600)
    for i in range(10):adapter.handle(str(i),"/check ادعا")
    assert len(adapter._last_result)<=3

def test_telegram_returns_safe_message_on_unexpected_failure():
    adapter=TelegramAdapter(PoliticalApplication(BrokenEngine()))
    text=adapter.handle("u","/check ادعا")
    assert "نتیجه قطعی ارائه نمی‌کنم" in text

def test_application_emits_failure_metric():
    sink=MemoryMetricsSink();app=PoliticalApplication(BrokenEngine(),metrics=sink)
    with pytest.raises(RuntimeError):app.check("secret")
    assert len(sink.rows)==1 and sink.rows[0].success is False and sink.rows[0].error_type=="RuntimeError"

def test_memory_metrics_sink_is_bounded():
    sink=MemoryMetricsSink(max_entries=3)
    app=PoliticalApplication(CountingEngine(),metrics=sink)
    for i in range(10):app.check(str(i))
    assert len(sink.rows)==3

def test_load_test_success_predicate_detects_logical_failure():
    result=run_load_test(lambda x:{"ok":x!=2},[1,2,3],concurrency=2,success_predicate=lambda r:r["ok"])
    assert result.successes==2 and result.functional_failures==1 and result.failures==1

def test_provider_stats_are_thread_local_under_concurrency():
    import threading
    inner=Searcher();provider=CachedSearchProvider(inner,MemoryCache(),0);seen=[];barrier=threading.Barrier(2)
    def worker(q):
        provider.reset_request_stats();barrier.wait();provider.search(q,1);seen.append(provider.stats)
    a=threading.Thread(target=worker,args=("a",));b=threading.Thread(target=worker,args=("b",));a.start();b.start();a.join();b.join()
    assert len(seen)==2 and all(row["provider_calls"]==1 for row in seen)
