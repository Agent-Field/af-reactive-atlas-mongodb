from pydantic import BaseModel, Field
from typing import Literal


class DocumentIntelligence(BaseModel):
    risk_score: float = Field(description="Risk score 0.0-1.0")
    risk_category: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk category"
    )
    pattern_match: str = Field(description="Detected pattern name, or 'none'")
    flags: list[str] = Field(description="Applicable rule IDs from the domain rules")
    summary: str = Field(description="2-3 sentence executive summary")


class PolicyEvaluation(BaseModel):
    policy_id: str = Field(description="ID of the policy evaluated")
    triggered: bool = Field(description="Whether the policy was triggered")
    action: str = Field(
        description="Action: enrich, escalate, investigate, flag, hold, none"
    )
    reasoning: str = Field(
        description="One sentence explaining why the policy did or did not trigger"
    )


class PolicyEvaluationList(BaseModel):
    evaluations: list[PolicyEvaluation] = Field(description="One evaluation per policy")


class CascadeResult(BaseModel):
    documents_affected: int = Field(description="Total documents updated in cascade")
    entity_updates: list[str] = Field(
        description="Entity IDs whose risk profiles were updated"
    )
    documents_reenriched: int = Field(
        description="Number of related documents re-enriched"
    )
    summary: str = Field(description="One paragraph summary of the cascade")
