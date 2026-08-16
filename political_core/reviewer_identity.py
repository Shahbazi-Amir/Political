from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any,Mapping,Protocol

@dataclass(frozen=True,slots=True)
class ReviewerIdentity:
    reviewer_id:str
    active:bool=True
    roles:frozenset[str]=field(default_factory=lambda:frozenset({"reviewer"}))
    assurance_level:str="registry_verified"
    def has_role(self,role:str)->bool:return role in self.roles or "admin" in self.roles

class ReviewerIdentityProvider(Protocol):
    def resolve(self,reviewer_id:str)->ReviewerIdentity|None:...

class StaticReviewerRegistry:
    def __init__(self,reviewers:Mapping[str,Any]|None=None)->None:
        self._reviewers={}
        for reviewer_id,value in (reviewers or {}).items():
            if isinstance(value,ReviewerIdentity):identity=value
            elif isinstance(value,Mapping):identity=ReviewerIdentity(str(reviewer_id),bool(value.get("active",True)),frozenset(str(x) for x in value.get("roles",["reviewer"])),str(value.get("assurance_level") or "registry_verified"))
            else:identity=ReviewerIdentity(str(reviewer_id))
            self._reviewers[identity.reviewer_id]=identity
    def add(self,reviewer_id:str,*,roles=None,active:bool=True,assurance_level:str="registry_verified")->ReviewerIdentity:
        reviewer_id=str(reviewer_id).strip()
        if not reviewer_id:raise ValueError("reviewer_id is required")
        identity=ReviewerIdentity(reviewer_id,active,frozenset(roles or {"reviewer"}),assurance_level);self._reviewers[reviewer_id]=identity;return identity
    def resolve(self,reviewer_id:str)->ReviewerIdentity|None:return self._reviewers.get(str(reviewer_id).strip())
    def can_review(self,reviewer_id:str,case:Mapping[str,Any],*,required_role:str="reviewer")->bool:
        identity=self.resolve(reviewer_id)
        if identity is None or not identity.active or not identity.has_role(required_role):return False
        preparer=str(case.get("preparer_id") or case.get("prepared_by") or "").strip()
        return not preparer or preparer.casefold()!=identity.reviewer_id.casefold()
