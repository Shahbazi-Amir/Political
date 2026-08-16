from __future__ import annotations
import threading,time
from collections import defaultdict,deque
from contextlib import contextmanager
from typing import Iterator

class SlidingWindowRateLimiter:
    def __init__(self,max_requests:int=6,window_seconds:float=60.0)->None:
        self.max_requests=max(1,int(max_requests));self.window_seconds=max(.001,float(window_seconds));self._events=defaultdict(deque);self._lock=threading.Lock()
    def allow(self,subject:str,*,now:float|None=None)->bool:
        now=time.monotonic() if now is None else float(now);key=str(subject);cutoff=now-self.window_seconds
        with self._lock:
            events=self._events[key]
            while events and events[0]<=cutoff:events.popleft()
            if len(events)>=self.max_requests:return False
            events.append(now);return True

class ConcurrencyLimiter:
    def __init__(self,max_concurrent:int=8)->None:self.max_concurrent=max(1,int(max_concurrent));self._semaphore=threading.BoundedSemaphore(self.max_concurrent)
    @contextmanager
    def slot(self,*,timeout:float=0.0)->Iterator[bool]:
        acquired=self._semaphore.acquire(timeout=max(0.0,float(timeout)))
        try:yield acquired
        finally:
            if acquired:self._semaphore.release()
