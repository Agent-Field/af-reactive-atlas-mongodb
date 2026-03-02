from pydantic import BaseModel, Field
from typing import List, Literal


class DocumentIntelligence(BaseModel):
    risk_score: float = Field(description="Risk score 0.0-1.0")
    risk_category: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk category"
    )
    pattern_match: str = Field(
        description="Detected pattern: layering, smurfing, velocity_anomaly, round_tripping, structuring, none"
    )
    compliance_flags: List[str] = Field(
        description="Applicable compliance rule IDs (e.g. BSA-002, FATF-003)"
    )
    summary: str = Field(description="2-3 sentence executive summary of the analysis")


class PolicyEvaluation(BaseModel):
    policy_id: str = Field(description="ID of the policy evaluated")
    triggered: bool = Field(description="Whether the policy was triggered")
    action: str = Field(
        description="Action taken or recommended: enrich, escalate, investigate, flag, none"
    )
    reasoning: str = Field(
        description="One sentence explaining why the policy did or did not trigger"
    )


class PolicyEvaluationList(BaseModel):
    evaluations: List[PolicyEvaluation] = Field(description="One evaluation per policy")


class CascadeResult(BaseModel):
    documents_affected: int = Field(description="Total documents updated in cascade")
    account_updates: List[str] = Field(
        description="Account IDs whose risk profiles were updated"
    )
    transactions_reenriched: int = Field(
        description="Number of related transactions re-enriched"
    )
    summary: str = Field(description="One paragraph summary of the cascade")
