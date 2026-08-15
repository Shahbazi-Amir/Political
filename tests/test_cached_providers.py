import tempfile
import unittest
from pathlib import Path
from political_core.cache import SQLiteCache
from political_core.cached_providers import CachedSearchProvider
from political_core.models import SearchResult

class Inner:
    def __init__(self): self.calls=0
    def search(self, query, limit): self.calls+=1; return [SearchResult('https://a.example/x','A','text')]

class CachedProviderTests(unittest.TestCase):
    def test_search_cache_avoids_second_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            inner=Inner(); cache=SQLiteCache(Path(tmp)/'c.db'); wrapped=CachedSearchProvider(inner, cache, 3600)
            wrapped.search('query', 5); wrapped.search('query', 5)
            self.assertEqual(inner.calls, 1)
            self.assertEqual(wrapped.hits, 1)

if __name__=='__main__': unittest.main()
