from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True,slots=True)
class PricingPolicy:
    version:str
    input_cost_per_million:float
    output_cost_per_million:float
    def estimate(self,input_tokens:int|None,output_tokens:int|None)->float|None:
        if input_tokens is None and output_tokens is None:return None
        value=(float(input_tokens or 0)/1_000_000)*self.input_cost_per_million+(float(output_tokens or 0)/1_000_000)*self.output_cost_per_million
        return round(value,8)

def pricing_from_values(version:str|None,input_cost:float|None,output_cost:float|None)->PricingPolicy|None:
    if not version or input_cost is None or output_cost is None:return None
    return PricingPolicy(version,float(input_cost),float(output_cost))
