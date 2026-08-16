from __future__ import annotations
import threading,time
from collections import OrderedDict,deque
from contextlib import contextmanager
from typing import Iterator

class SlidingWindowRateLimiter:
    def __init__(self,max_requests:int=6,window_seconds:float=60.0,*,max_subjects:int=10000)->None:
        self.max_requests=max(1,int(max_requests));self.window_seconds=max(.001,float(window_seconds));self.max_subjects=max(100,int(max_subjects));self._events:OrderedDict[str,deque]=OrderedDict();self._lock=threading.Lock()
    def _cleanup(self,now:float)->None:
        cutoff=now-self.window_seconds
        stale=[]
        for key,events in self._events.items():
            while events and events[0]<=cutoff:events.popleft()
            if not events:stale.append(key)
        for key in stale:self._events.pop(key,None)
        while len(self._events)>self.max_subjects:self._events.popitem(last=False)
    def allow(self,subject:str,*,now:float|None=None)->bool:
        now=time.monotonic() if now is None else float(now);key=str(subject);cutoff=now-self.window_seconds
        with self._lock:
            events=self._events.get(key)
            if events is None:events=deque();self._events[key]=events
            else:self._events.move_to_end(key)
            while events and events[0]<=cutoff:events.popleft()
            if len(events)>=self.max_requests:return False
            events.append(now)
            if len(self._events)>self.max_subjects:self._cleanup(now)
            return True
    def __len__(self)->int:
        with self._lock:return len(self._events)

class ConcurrencyLimiter:
    def __init__(self,max_concurrent:int=8)->None:self.max_concurrent=max(1,int(max_concurrent));self._semaphore=threading.BoundedSemaphore(self.max_concurrent)
    @contextmanager
    def slot(self,*,timeout:float=0.0)->Iterator[bool]:
        acquired=self._semaphore.acquire(timeout=max(0.0,float(timeout)))
        try:yield acquired
        finally:
            if acquired:self._semaphore.release()
