"""Evidence-first political fact-checking core."""
from .engine import FactCheckEngine
from .models import Budget,FactCheckResult,Verdict
__all__=["Budget","FactCheckEngine","FactCheckResult","Verdict"]
