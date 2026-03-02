from pydantic import BaseModel, Field
from typing import Literal


class Evidence(BaseModel):
    fact: str = Field(description="Specific observable fact")
    source: str = Field(
        description="Where evidence came from: entity_profile, transaction_history, rules, counterparty_context, domain_patterns"
    )
    weight: Literal["strong", "moderate", "weak"] = Field(
        description="How strongly this evidence supports the assessment"
    )


class TriageResult(BaseModel):
    priority: Literal["low", "routine", "elevated", "urgent", "critical"] = Field(
        description="Triage priority level"
    )
    signals: list[str] = Field(description="Initial observations from quick scan")
    investigation_needed: bool = Field(
        description="Whether deep investigation is warranted"
    )
    investigation_focus: list[str] = Field(
        default_factory=list,
        description="Areas to investigate deeper: counterparty_history, network_analysis, velocity_check, jurisdiction_risk, pattern_search",
    )


class DocumentIntelligence(BaseModel):
    risk_score: float = Field(description="Risk score 0.0-1.0")
    risk_category: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk category"
    )
    pattern_match: str = Field(description="Detected pattern name, or 'none'")
    flags: list[str] = Field(description="Applicable rule IDs from the domain rules")
    summary: str = Field(description="2-3 sentence executive summary")
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Specific facts that drove the assessment",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Actions: hold, escalate, review_counterparty, enhanced_monitoring, clear, investigate_network",
    )
    confidence: float = Field(
        default=0.5, description="Confidence in assessment 0.0-1.0"
    )
    related_entities_flagged: list[str] = Field(
        default_factory=list,
        description="Entity IDs warranting investigation",
    )
    investigation_depth: Literal["triage_only", "standard", "deep"] = Field(
        default="standard",
        description="How deeply this document was investigated",
    )


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


class NetworkInsight(BaseModel):
    summary: str = Field(
        description="Network-level summary of connected entities and risk propagation"
    )
    entities_involved: list[str] = Field(
        default_factory=list,
        description="All entity IDs in the network",
    )
    total_exposure: float = Field(
        default=0.0,
        description="Total monetary exposure across the network",
    )
    risk_pattern: str = Field(
        default="isolated",
        description="Network-level pattern: chain, ring, hub, cluster, isolated",
    )


class CascadeResult(BaseModel):
    documents_affected: int = Field(description="Total documents updated in cascade")
    entity_updates: list[str] = Field(
        description="Entity IDs whose risk profiles were updated"
    )
    documents_reenriched: int = Field(
        description="Number of related documents re-enriched"
    )
    summary: str = Field(description="One paragraph summary of the cascade")
    network_insight: NetworkInsight | None = Field(
        default=None, description="Network-level analysis if available"
    )
