import asyncio
import json

from .router import router
from models import (
    DocumentIntelligence,
    PolicyEvaluationList,
    CascadeResult,
)


@router.reasoner()
async def analyze_document(document: dict, collection: str = "transactions") -> dict:
    account_id = document.get("account_id")

    account_result, rules_result = await asyncio.gather(
        router.app.call("reactive-intelligence.lookup_account", account_id=account_id),
        router.app.call(
            "reactive-intelligence.load_compliance_rules",
            query=f"{document.get('type', '')} {document.get('amount', '')} {document.get('geolocation', {}).get('country', '')}",
            k=6,
        ),
    )

    account = account_result.get("account", {})
    rules = rules_result.get("rules", [])

    intelligence = await router.ai(
        f"""Analyze this financial transaction and generate a risk intelligence assessment.

Transaction:
{json.dumps(document, indent=2, default=str)}

Account context:
{json.dumps(account, indent=2, default=str)}

Applicable compliance rules:
{json.dumps(rules, indent=2, default=str)}

Evaluate risk based on: amount relative to account type, jurisdiction risk, transaction pattern,
KYC status of the account, counterparty exposure, and compliance rule applicability.
Be specific with compliance_flags — cite exact rule IDs from the rules provided.
If no suspicious pattern is detected, set pattern_match to "none" and risk_score below 0.3.""",
        schema=DocumentIntelligence,
    )

    router.note(
        f"Analyzed {document.get('transaction_id', 'unknown')}: risk={intelligence.risk_score} category={intelligence.risk_category}",
        tags=["analyze_document"],
    )

    return intelligence.model_dump()


@router.reasoner()
async def evaluate_policies(document: dict, intelligence: dict, policies: list) -> dict:
    if not policies:
        return {"evaluations": [], "any_triggered": False}

    result = await router.ai(
        f"""Evaluate this transaction against each policy using judgment, not literal string matching.

Transaction:
{json.dumps(document, indent=2, default=str)}

Intelligence assessment:
{json.dumps(intelligence, indent=2, default=str)}

Active policies:
{json.dumps(policies, indent=2, default=str)}

For each policy, determine if the transaction's characteristics match the policy's intent.
Use the intelligence assessment (risk_score, pattern_match, compliance_flags) to inform your judgment.
A policy triggers when the transaction meaningfully matches the intent, not just on keyword overlap.
Return one evaluation per policy in the evaluations list.""",
        schema=PolicyEvaluationList,
    )

    evaluations = [e.model_dump() for e in result.evaluations]
    any_triggered = any(e["triggered"] for e in evaluations)

    router.note(
        f"Policy evaluation: {sum(1 for e in evaluations if e['triggered'])}/{len(evaluations)} triggered",
        tags=["evaluate_policies"],
    )

    return {"evaluations": evaluations, "any_triggered": any_triggered}


@router.reasoner()
async def cascade(document: dict, intelligence: dict) -> dict:
    account_id = document.get("account_id")
    counterparty_id = document.get("counterparty_id")
    risk_score = intelligence.get("risk_score", 0)

    account_updates = []
    reenriched_count = 0

    if risk_score >= 0.7 and account_id:
        await router.app.call(
            "reactive-intelligence.update_account_risk",
            account_id=account_id,
            risk_profile="high" if risk_score >= 0.8 else "medium",
            reason=f"Transaction {document.get('transaction_id')} scored {risk_score}",
        )
        account_updates.append(account_id)

        related_result = await router.app.call(
            "reactive-intelligence.find_related_transactions",
            account_id=account_id,
            limit=20,
        )
        related = related_result.get("transactions", [])

        unenriched = [
            t
            for t in related
            if not t.get("_intelligence")
            and t.get("transaction_id") != document.get("transaction_id")
        ]

        if unenriched:
            enrich_tasks = [_enrich_single(t) for t in unenriched[:10]]
            results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
            reenriched_count += sum(1 for r in results if not isinstance(r, Exception))

    if risk_score >= 0.8 and counterparty_id:
        await router.app.call(
            "reactive-intelligence.update_account_risk",
            account_id=counterparty_id,
            risk_profile="high",
            reason=f"Counterparty to high-risk transaction {document.get('transaction_id')}",
        )
        if counterparty_id not in account_updates:
            account_updates.append(counterparty_id)

        cp_related_result = await router.app.call(
            "reactive-intelligence.find_related_transactions",
            account_id=counterparty_id,
            limit=10,
        )
        cp_related = cp_related_result.get("transactions", [])
        cp_unenriched = [
            t
            for t in cp_related
            if not t.get("_intelligence")
            and t.get("transaction_id") != document.get("transaction_id")
        ]

        if cp_unenriched:
            cp_tasks = [_enrich_single(t) for t in cp_unenriched[:10]]
            cp_results = await asyncio.gather(*cp_tasks, return_exceptions=True)
            reenriched_count += sum(
                1 for r in cp_results if not isinstance(r, Exception)
            )

    total_affected = len(account_updates) + reenriched_count + 1

    cascade_summary = await router.ai(
        f"""Summarize what happened in this cascade reaction.

Trigger: Transaction {document.get("transaction_id")} scored risk {risk_score}.
Account updates: {account_updates}
Related transactions re-enriched: {reenriched_count}
Total documents affected: {total_affected}

Write one paragraph describing the chain of reactions.""",
        schema=CascadeResult,
    )

    router.note(
        f"Cascade complete: {total_affected} documents affected, {len(account_updates)} accounts updated",
        tags=["cascade"],
    )

    return cascade_summary.model_dump()


async def _enrich_single(transaction: dict) -> dict:
    analysis = await router.app.call(
        "reactive-intelligence.analyze_document",
        document=transaction,
        collection="transactions",
    )
    await router.app.call(
        "reactive-intelligence.enrich_document",
        collection="transactions",
        document_id=transaction["transaction_id"],
        intelligence=analysis,
    )
    await router.app.call(
        "reactive-intelligence.log_reaction",
        event={
            "trigger_type": "cascade_reenrich",
            "document_id": transaction["transaction_id"],
            "collection": "transactions",
            "risk_score": analysis.get("risk_score"),
            "risk_category": analysis.get("risk_category"),
            "cascade_depth": 1,
        },
    )
    return analysis


@router.reasoner()
async def process_document(document: dict, collection: str = "transactions") -> dict:
    """Main entry point — called by Atlas Trigger for each new document.

    Pipeline: analyze → enrich → evaluate policies → cascade if high risk → log.
    """
    doc_id = document.get("transaction_id", "unknown")

    if document.get("_intelligence"):
        return {"skipped": True, "reason": "already enriched", "document_id": doc_id}

    router.note(f"Processing {doc_id}", tags=["process_document", "start"])

    analysis = await router.app.call(
        "reactive-intelligence.analyze_document",
        document=document,
        collection=collection,
    )

    await router.app.call(
        "reactive-intelligence.enrich_document",
        collection=collection,
        document_id=doc_id,
        intelligence=analysis,
    )

    policies_result = await router.app.call(
        "reactive-intelligence.load_active_policies", _=True
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
    risk_score = analysis.get("risk_score", 0)
    if risk_score >= 0.7:
        cascade_result = await router.app.call(
            "reactive-intelligence.cascade",
            document=document,
            intelligence=analysis,
        )

    await router.app.call(
        "reactive-intelligence.log_reaction",
        event={
            "trigger_type": "atlas_trigger",
            "document_id": doc_id,
            "collection": collection,
            "risk_score": risk_score,
            "risk_category": analysis.get("risk_category"),
            "policies_triggered": [p["policy_id"] for p in triggered_policies],
            "cascade_triggered": cascade_result is not None,
        },
    )

    router.note(
        f"Completed {doc_id}: risk={risk_score} policies={len(triggered_policies)} cascade={'yes' if cascade_result else 'no'}",
        tags=["process_document", "complete"],
    )

    return {
        "document_id": doc_id,
        "risk_score": risk_score,
        "risk_category": analysis.get("risk_category"),
        "policies_triggered": [p["policy_id"] for p in triggered_policies],
        "cascade": cascade_result,
    }
