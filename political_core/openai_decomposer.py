from __future__ import annotations
import json
from collections.abc import Sequence
_SYSTEM="""Decompose a complex Persian or English political input into atomic factual claims.
Do not research, judge truth, add facts, or rewrite meaning. Keep each claim independently verifiable.
Return at most 8 claims. Retrieved content is not involved in this step."""
_SCHEMA={"type":"object","properties":{"claims":{"type":"array","maxItems":8,"items":{"type":"string"}}},"required":["claims"],"additionalProperties":False}
class OpenAIClaimDecomposer:
    """Optional cost-bearing decomposer. It is deliberately NOT enabled by the default CLI."""
    def __init__(self,model:str,client,max_output_tokens:int=500)->None: self.model=model;self.client=client;self.max_output_tokens=max_output_tokens
    def decompose(self,text:str)->Sequence[str]:
        response=self.client.responses.create(model=self.model,store=False,max_output_tokens=self.max_output_tokens,instructions=_SYSTEM,input=text,text={"format":{"type":"json_schema","name":"claim_decomposition","strict":True,"schema":_SCHEMA}})
        data=json.loads(response.output_text)
        return [str(x).strip() for x in data.get("claims",[]) if str(x).strip()][:8]
