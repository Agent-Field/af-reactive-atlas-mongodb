# pyright: reportImportCycles=false

import asyncio
import json
from typing import Any

from models import (
    CascadeResult,
    DocumentIntelligence,
    NetworkInsight,
    PolicyEvaluationList,
    TriageResult,
)

from .router import router


def _build_rule_query(document: dict[str, Any]) -> str:
    geo = document.get("geolocation") or document.get("shipping_address") or {}
    items = document.get("items", [])
    categories = " ".join(
        str(item.get("category", "")) for item in items if isinstance(item, dict)
    )
    parts = [
        str(document.get("type", "")),
        str(document.get("amount", "")),
        str(geo.get("country", "")) if isinstance(geo, dict) else "",
        str(document.get("narrative", "")),
        categories,
        str(document.get("shipping_method", "")),
    ]
    return " ".join(p for p in parts if p).strip()


@router.reasoner()
async def triage_document(
    document: dict[str, Any],
    domain_config: dict[str, Any],
) -> dict[str, Any]:
    triage_result = await router.ai(
        f"""You are performing a rapid triage assessment on an incoming {domain_config.get("display_name") or domain_config.get("domain") or "domain"} document.
Do NOT do a full analysis - this is a quick screen to determine if deeper investigation is warranted.

Look for:
- Amount anomalies (round numbers, just-below-threshold values, unusually high/low)
- Narrative red flags (vague descriptions, mismatched purpose)
- Jurisdiction risk signals (high-risk countries, cross-border patterns)
- Transaction type risk (cash, wire, crypto - higher inherent risk)
- Velocity indicators (timestamps suggesting rapid sequence)
- Entity signals (account type, age, verification status hints in the document)

Set investigation_needed=True if ANY meaningful signal exists.
Set investigation_needed=False ONLY for clearly routine/normal documents.
When in doubt, investigate.

investigation_focus should list specific areas: counterparty_history, network_analysis, velocity_check, jurisdiction_risk, pattern_search

Domain info:
{json.dumps({"domain": domain_config.get("domain"), "display_name": domain_config.get("display_name")}, indent=2)}

Raw document:
{json.dumps(document, indent=2, default=str)}""",
        schema=TriageResult,
    )

    return triage_result.model_dump()


@router.reasoner()
async def analyze_document(
    document: dict[str, Any],
    domain_config: dict[str, Any],
    triage_signals: list[str] | None = None,
    counterparty_context: dict[str, Any] | None = None,
    recent_high_risk: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context_loading = domain_config.get("context_loading", {})
    entity_lookup_field = context_loading.get("entity_lookup_field")
    history_collection = context_loading.get("history_collection")
    history_match_fields = context_loading.get("history_match_fields", [])
    history_limit = int(context_loading.get("history_limit", 50))
    entity_collection = domain_config.get("entity_collection")
    entity_id_field = domain_config.get("entity_id_field")
    rules_collection = domain_config.get("rules_collection")

    entity_id = document.get(entity_lookup_field) if entity_lookup_field else None

    entity_task = router.app.call(
        "reactive-intelligence.load_entity_context",
        entity_id=str(entity_id) if entity_id is not None else "",
        entity_collection=entity_collection,
        entity_id_field=entity_id_field,
    )
    rules_task = router.app.call(
        "reactive-intelligence.load_rules",
        query=_build_rule_query(document),
        rules_collection=rules_collection,
        k=6,
    )

    related_tasks: list[Any] = []
    for field_name in history_match_fields:
        value = document.get(field_name)
        if value is not None and history_collection:
            related_tasks.append(
                router.app.call(
                    "reactive-intelligence.find_related_documents",
                    collection=history_collection,
                    match_field=field_name,
                    match_value=str(value),
                    limit=history_limit,
                )
            )

    gathered = await asyncio.gather(entity_task, rules_task, *related_tasks)
    entity_result = gathered[0]
    rules_result = gathered[1]
    related_results = gathered[2:]

    entity = entity_result.get("entity", {})
    rules = rules_result.get("rules", [])

    related_documents_map: dict[str, dict[str, Any]] = {}
    doc_id_field = domain_config.get("document_id_field")
    for result in related_results:
        for related_doc in result.get("documents", []):
            key = related_doc.get(doc_id_field) if doc_id_field else None
            if key:
                related_documents_map[str(key)] = related_doc

    related_documents = list(related_documents_map.values())
    deep_context_available = bool(counterparty_context) or bool(recent_high_risk)

    intelligence = await router.ai(
        f"""{domain_config.get("analysis_prompt", "Analyze this document for risk.")}

Domain:
{json.dumps({"domain": domain_config.get("domain"), "display_name": domain_config.get("display_name")}, indent=2)}

Document:
{json.dumps(document, indent=2, default=str)}

Primary entity context:
{json.dumps(entity, indent=2, default=str)}

Related history:
{json.dumps(related_documents, indent=2, default=str)}

Applicable rules:
{json.dumps(rules, indent=2, default=str)}

Triage signals (from initial assessment):
{json.dumps(triage_signals or [], indent=2, default=str)}

Counterparty intelligence:
{json.dumps(counterparty_context or {}, indent=2, default=str)}

Recent high-risk activity in this domain:
{json.dumps(recent_high_risk or [], indent=2, default=str)}

Expected enrichment schema:
{json.dumps(domain_config.get("enrichment_schema", {}), indent=2)}

Return a structured assessment with realistic confidence and clear rationale.

Requirements:
- Provide 3-6 evidence items with specific facts, source, and weight.
- Recommend concrete actions from: hold, escalate, review_counterparty, enhanced_monitoring, clear, investigate_network.
- Set confidence based on quality and consistency of evidence.
- Populate related_entities_flagged with entity IDs that warrant attention.
- Set investigation_depth to "deep" if counterparty/network context is available, otherwise "standard".
- If counterparty context indicates recent outgoing transactions to third parties, explicitly look for CHAIN PATTERNS (A->B->C) and reflect that in pattern_match, summary, and recommended_actions when relevant.
- Avoid generic statements; ground judgments in facts from the document and context.

Deep context available: {deep_context_available}""",
        schema=DocumentIntelligence,
    )

    return intelligence.model_dump()


@router.reasoner()
async def evaluate_policies(
    document: dict[str, Any],
    intelligence: dict[str, Any],
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    if not policies:
        return {"evaluations": [], "any_triggered": False}

    result = await router.ai(
        f"""Evaluate this document against each policy using judgment, not literal string matching.

Document:
{json.dumps(document, indent=2, default=str)}

Intelligence assessment:
{json.dumps(intelligence, indent=2, default=str)}

Active policies:
{json.dumps(policies, indent=2, default=str)}

For each policy, determine if the document's characteristics match the policy's intent.
Use the intelligence assessment (risk_score, pattern_match, flags) to inform your judgment.
A policy triggers when the document meaningfully matches the intent, not just on keyword overlap.
Return one evaluation per policy in the evaluations list.""",
        schema=PolicyEvaluationList,
    )

    evaluations = [e.model_dump() for e in result.evaluations]
    any_triggered = any(e["triggered"] for e in evaluations)

    return {"evaluations": evaluations, "any_triggered": any_triggered}


@router.reasoner()
async def generate_network_insight(
    document: dict[str, Any],
    intelligence: dict[str, Any],
    domain_config: dict[str, Any],
    related_high_risk: list[dict[str, Any]],
    entity_updates: list[str],
) -> dict[str, Any]:
    network_insight = await router.ai(
        f"""Generate a network-level intelligence view from a triggered high-risk document.

Domain:
{json.dumps({"domain": domain_config.get("domain"), "display_name": domain_config.get("display_name")}, indent=2)}

Triggering document:
{json.dumps(document, indent=2, default=str)}

Triggering intelligence:
{json.dumps(intelligence, indent=2, default=str)}

Recently flagged high-risk documents:
{json.dumps(related_high_risk, indent=2, default=str)}

Entities updated during cascade:
{json.dumps(entity_updates, indent=2, default=str)}

Tasks:
- Identify network pattern: chain (A->B->C), ring (A->B->C->A), hub (one entity connected to many), cluster (group), or isolated.
- Calculate total monetary exposure across the observed network.
- List all entities involved in entities_involved.
- Write a concise, actionable network summary.

Use only evidence in provided data and avoid speculation.""",
        schema=NetworkInsight,
    )
    return network_insight.model_dump()


@router.reasoner()
async def cascade(
    document: dict[str, Any],
    intelligence: dict[str, Any],
    domain_config: dict[str, Any],
) -> dict[str, Any]:
    cascade_config = domain_config.get("cascade_config", {})
    context_loading = domain_config.get("context_loading", {})

    entity_collection = domain_config.get("entity_collection")
    entity_id_field = domain_config.get("entity_id_field")
    document_collection = domain_config.get("document_collection")
    document_id_field = domain_config.get("document_id_field")

    entity_lookup_field = context_loading.get("entity_lookup_field")
    counterparty_field = context_loading.get("counterparty_field")
    history_collection = context_loading.get("history_collection", document_collection)

    risk_score = float(intelligence.get("risk_score", 0))
    risk_threshold = float(cascade_config.get("risk_threshold", 0.7))
    ct_raw = cascade_config.get("counterparty_threshold")
    counterparty_threshold = float(ct_raw) if ct_raw is not None else float("inf")
    update_entities = bool(cascade_config.get("update_entities", True))
    reenrich_related = bool(cascade_config.get("reenrich_related", True))
    max_reenrich = int(cascade_config.get("max_reenrich", 10))

    entity_updates: list[str] = []
    documents_reenriched = 0
    trigger_doc_id = (
        document.get(document_id_field) if isinstance(document_id_field, str) else None
    )

    entity_lookup_key = (
        entity_lookup_field if isinstance(entity_lookup_field, str) else None
    )
    counterparty_key = (
        counterparty_field if isinstance(counterparty_field, str) else None
    )
    doc_id_key = document_id_field if isinstance(document_id_field, str) else None

    if risk_score >= risk_threshold and update_entities and entity_lookup_key:
        entity_id = document.get(entity_lookup_key)
        if entity_id is not None:
            await router.app.call(
                "reactive-intelligence.update_entity_risk",
                entity_collection=entity_collection,
                entity_id_field=entity_id_field,
                entity_id=str(entity_id),
                risk_profile="high" if risk_score >= 0.8 else "medium",
                reason=f"Document {trigger_doc_id} scored {risk_score}",
            )
            entity_updates.append(str(entity_id))

        if reenrich_related and entity_id is not None:
            related_result = await router.app.call(
                "reactive-intelligence.find_related_documents",
                collection=history_collection,
                match_field=entity_lookup_key,
                match_value=str(entity_id),
                limit=max_reenrich * 2,
            )
            related = related_result.get("documents", [])
            unenriched = [
                d
                for d in related
                if not d.get("_intelligence")
                and (d.get(doc_id_key) if doc_id_key else None) != trigger_doc_id
            ]
            if unenriched:
                tasks = [
                    _enrich_single(d, domain_config) for d in unenriched[:max_reenrich]
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                documents_reenriched += sum(
                    1 for result in results if not isinstance(result, Exception)
                )

    if (
        risk_score >= counterparty_threshold
        and update_entities
        and counterparty_key
        and document.get(counterparty_key) is not None
    ):
        counterparty_id = str(document.get(counterparty_key))
        await router.app.call(
            "reactive-intelligence.update_entity_risk",
            entity_collection=entity_collection,
            entity_id_field=entity_id_field,
            entity_id=counterparty_id,
            risk_profile="high",
            reason=f"Counterparty to high-risk document {trigger_doc_id}",
        )
        if counterparty_id not in entity_updates:
            entity_updates.append(counterparty_id)

    recent_high_risk_result = await router.app.call(
        "reactive-intelligence.find_recent_high_risk",
        collection=document_collection,
        min_risk_score=0.6,
        hours_window=48,
        limit=max(20, max_reenrich * 2),
    )
    related_high_risk = recent_high_risk_result.get("documents", [])

    network_insight = await router.app.call(
        "reactive-intelligence.generate_network_insight",
        document=document,
        intelligence=intelligence,
        domain_config=domain_config,
        related_high_risk=related_high_risk,
        entity_updates=entity_updates,
    )

    await router.app.call(
        "reactive-intelligence.log_reaction",
        event={
            "trigger_type": "network_insight",
            "domain": domain_config.get("domain"),
            "document_id": trigger_doc_id,
            "collection": document_collection,
            "risk_score": risk_score,
            "entity_updates": entity_updates,
            "network_pattern": network_insight.get("risk_pattern"),
            "network_exposure": network_insight.get("total_exposure"),
            "network_summary": network_insight.get("summary"),
        },
    )

    documents_affected = 1 + len(entity_updates) + documents_reenriched
    summary = (
        f"Cascade for {trigger_doc_id} updated {len(entity_updates)} entities "
        f"and re-enriched {documents_reenriched} related documents."
    )

    result = CascadeResult(
        documents_affected=documents_affected,
        entity_updates=entity_updates,
        documents_reenriched=documents_reenriched,
        summary=summary,
        network_insight=NetworkInsight.model_validate(network_insight)
        if network_insight
        else None,
    )

    return result.model_dump()


async def _enrich_single(
    document: dict[str, Any],
    domain_config: dict[str, Any],
) -> dict[str, Any]:
    doc_collection = domain_config.get("document_collection")
    doc_id_field = domain_config.get("document_id_field")
    doc_id = document.get(doc_id_field) if isinstance(doc_id_field, str) else None

    analysis = await router.app.call(
        "reactive-intelligence.analyze_document",
        document=document,
        domain_config=domain_config,
    )
    await router.app.call(
        "reactive-intelligence.enrich_document",
        collection=doc_collection,
        id_field=doc_id_field,
        document_id=str(doc_id),
        intelligence=analysis,
    )
    await router.app.call(
        "reactive-intelligence.log_reaction",
        event={
            "trigger_type": "cascade_reenrich",
            "document_id": doc_id,
            "collection": doc_collection,
            "domain": domain_config.get("domain"),
            "risk_score": analysis.get("risk_score"),
            "risk_category": analysis.get("risk_category"),
            "cascade_depth": 1,
        },
    )
    return analysis


@router.reasoner()
async def process_document(
    document: dict[str, Any],
    collection: str,
    domain: str = "finance",
) -> dict[str, Any]:
    config_result = await router.app.call(
        "reactive-intelligence.load_domain_config",
        domain=domain,
    )
    domain_config = config_result.get("config")
    if not domain_config:
        raise ValueError(f"Domain config not found for domain={domain}")

    doc_id_field = domain_config.get("document_id_field", "id")
    doc_id = document.get(doc_id_field, "unknown")

    if document.get("_intelligence"):
        return {"skipped": True, "reason": "already enriched", "document_id": doc_id}

    triage = await router.app.call(
        "reactive-intelligence.triage_document",
        document=document,
        domain_config=domain_config,
    )

    context_loading = domain_config.get("context_loading", {})
    investigation_needed = bool(triage.get("investigation_needed"))
    investigation_depth = "standard"

    if investigation_needed:
        counterparty_field = context_loading.get("counterparty_field")
        counterparty_context_task = None
        if (
            isinstance(counterparty_field, str)
            and document.get(counterparty_field) is not None
        ):
            counterparty_context_task = router.app.call(
                "reactive-intelligence.find_counterparty_context",
                counterparty_id=str(document[counterparty_field]),
                entity_collection=domain_config["entity_collection"],
                entity_id_field=domain_config["entity_id_field"],
                document_collection=domain_config.get("context_loading", {}).get(
                    "history_collection", domain_config["document_collection"]
                ),
                entity_lookup_field=domain_config.get("context_loading", {}).get(
                    "entity_lookup_field", domain_config["entity_id_field"]
                ),
                limit=int(context_loading.get("counterparty_history_limit", 20)),
            )

        recent_high_risk_task = router.app.call(
            "reactive-intelligence.find_recent_high_risk",
            collection=domain_config["document_collection"],
            min_risk_score=0.6,
            hours_window=48,
            limit=int(context_loading.get("recent_high_risk_limit", 20)),
        )

        if counterparty_context_task is not None:
            counterparty_result, recent_high_risk_result = await asyncio.gather(
                counterparty_context_task,
                recent_high_risk_task,
            )
            counterparty_context = counterparty_result
        else:
            recent_high_risk_result = await recent_high_risk_task
            counterparty_context = None

        analysis = await router.app.call(
            "reactive-intelligence.analyze_document",
            document=document,
            domain_config=domain_config,
            triage_signals=triage.get("signals") or [],
            counterparty_context=counterparty_context,
            recent_high_risk=recent_high_risk_result.get("documents") or [],
        )
        investigation_depth = "deep"
    else:
        analysis = await router.app.call(
            "reactive-intelligence.analyze_document",
            document=document,
            domain_config=domain_config,
        )
        investigation_depth = "standard"

    risk_score = float(analysis.get("risk_score", 0))
    if not investigation_needed and risk_score < 0.2:
        investigation_depth = "triage_only"

    analysis["investigation_depth"] = investigation_depth

    await router.app.call(
        "reactive-intelligence.enrich_document",
        collection=collection,
        id_field=doc_id_field,
        document_id=str(doc_id),
        intelligence=analysis,
    )

    policies_result = await router.app.call(
        "reactive-intelligence.load_active_policies",
        domain=domain,
    )
    policies = policies_result.get("policies", [])

    policy_result = await router.app.call(
        "reactive-intelligence.evaluate_policies",
        document=document,
        intelligence=analysis,
        policies=policies,
    )
    triggered_policies = [
        e for e in policy_result.get("evaluations", []) if e.get("triggered")
    ]

    cascade_result = None
    if risk_score >= float(
        domain_config.get("cascade_config", {}).get("risk_threshold", 0.7)
    ):
        cascade_result = await router.app.call(
            "reactive-intelligence.cascade",
            document=document,
            intelligence=analysis,
            domain_config=domain_config,
        )

    await router.app.call(
        "reactive-intelligence.log_reaction",
        event={
            "trigger_type": "atlas_trigger",
            "domain": domain,
            "document_id": doc_id,
            "collection": collection,
            "risk_score": risk_score,
            "risk_category": analysis.get("risk_category"),
            "triage_priority": triage.get("priority"),
            "investigation_depth": investigation_depth,
            "triage_signals": triage.get("signals") or [],
            "policies_triggered": [p["policy_id"] for p in triggered_policies],
            "cascade_triggered": cascade_result is not None,
        },
    )

    return {
        "domain": domain,
        "document_id": doc_id,
        "triage": triage,
        "investigation_depth": investigation_depth,
        "risk_score": risk_score,
        "risk_category": analysis.get("risk_category"),
        "policies_triggered": [p["policy_id"] for p in triggered_policies],
        "cascade": cascade_result,
    }
