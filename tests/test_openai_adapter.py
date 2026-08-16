from __future__ import annotations
import json,pytest
from political_core.models import Evidence,SourceKind,SourceRole
from political_core.openai_reasoning import OpenAIReasoningProvider,ReasoningSchemaError,ReasoningTimeout
def evidence():return [Evidence("E1","https://a.example/x","A","a.example","text",None,SourceKind.NEWSROOM,.7,"a.example",source_role=SourceRole.SECONDARY_REPORTING)]
class Resp:
    def __init__(self,text):self.output_text=text;self.usage=None;self.output=[]
class Responses:
    def __init__(self,seq):self.seq=list(seq);self.calls=0
    def create(self,**kwargs):
        self.calls+=1;item=self.seq.pop(0)
        if isinstance(item,Exception):raise item
        return item
class Client:
    def __init__(self,seq):self.responses=Responses(seq)
def good_json(verdict="true"):return json.dumps({"verdict":verdict,"confidence":.7,"summary":"ok","key_points":[],"uncertainty":"","citation_ids":["E1"],"conflict_detected":False,"conflict_resolution":"","evidence_stances":[{"id":"E1","stance":"supports"}],"missing_evidence":[],"contradictions":[]})
def test_schema_failure_retries_once_then_succeeds():
    client=Client([Resp("{bad"),Resp(good_json())]);d=OpenAIReasoningProvider("x",client=client,max_retries=1).evaluate("claim",evidence());assert d.verdict.value=="true";assert client.responses.calls==2
def test_schema_failure_does_not_retry_forever():
    client=Client([Resp("{bad"),Resp("{bad")]);p=OpenAIReasoningProvider("x",client=client,max_retries=1)
    with pytest.raises(ReasoningSchemaError):p.evaluate("claim",evidence())
    assert client.responses.calls==2
def test_timeout_classified_and_retry_limited():
    client=Client([TimeoutError("timeout"),TimeoutError("timeout")]);p=OpenAIReasoningProvider("x",client=client,max_retries=1)
    with pytest.raises(ReasoningTimeout):p.evaluate("claim",evidence())
    assert client.responses.calls==2
def test_critic_uses_second_call():
    client=Client([Resp(good_json()),Resp(good_json("unverified"))]);p=OpenAIReasoningProvider("x",client=client,max_retries=0);first=p.evaluate("claim",evidence());second=p.critique("claim",evidence(),first);assert first.verdict.value=="true" and second.verdict.value=="unverified";assert client.responses.calls==2
