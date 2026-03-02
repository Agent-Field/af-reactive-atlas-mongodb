import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, MongoClient

from .router import router


_client: MongoClient[dict[str, Any]] | None = None
_db = None


def _get_db():
    global _client, _db
    if _db is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI is not set")
        _client = MongoClient(uri)
        _db = _client[os.getenv("MONGODB_DATABASE", "reactive_intelligence")]
    return _db


def _serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@router.skill()
def load_domain_config(domain: str) -> dict[str, Any]:
    db = _get_db()
    config = db["domain_config"].find_one({"domain": domain}, {"_id": 0})
    return {"ok": True, "found": config is not None, "config": config}


@router.skill()
def load_entity_context(
    entity_id: str, entity_collection: str, entity_id_field: str
) -> dict[str, Any]:
    db = _get_db()
    entity = db[entity_collection].find_one({entity_id_field: entity_id}, {"_id": 0})
    return {"ok": True, "found": entity is not None, "entity": entity}


@router.skill()
def find_related_documents(
    collection: str,
    match_field: str,
    match_value: str,
    limit: int = 50,
) -> dict[str, Any]:
    db = _get_db()
    query: dict[str, Any] = {match_field: match_value}

    docs = list(
        db[collection]
        .find(query, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .limit(int(limit))
    )
    return {"ok": True, "count": len(docs), "documents": _serialize(docs)}


@router.skill()
def load_rules(query: str, rules_collection: str, k: int = 6) -> dict[str, Any]:
    db = _get_db()
    docs = list(
        db[rules_collection]
        .find(
            {"$text": {"$search": query}},
            {"_id": 0, "score": {"$meta": "textScore"}},
        )
        .sort([("score", {"$meta": "textScore"})])
        .limit(int(k))
    )
    return {"ok": True, "count": len(docs), "rules": docs}


@router.skill()
def enrich_document(
    collection: str,
    id_field: str,
    document_id: str,
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    db = _get_db()
    enrichment = dict(intelligence)
    enrichment["analyzed_at"] = datetime.now(timezone.utc)
    enrichment["version"] = 1

    existing = db[collection].find_one({id_field: document_id})
    if existing and existing.get("_intelligence"):
        enrichment["version"] = existing["_intelligence"].get("version", 0) + 1

    db[collection].update_one(
        {id_field: document_id},
        {"$set": {"_intelligence": enrichment}},
    )

    return {"ok": True, "document_id": document_id, "enriched": True}


@router.skill()
def load_active_policies(domain: str) -> dict[str, Any]:
    db = _get_db()
    policies = list(db["policies"].find({"active": True, "domain": domain}, {"_id": 0}))
    return {"ok": True, "count": len(policies), "policies": policies}


@router.skill()
def update_entity_risk(
    entity_collection: str,
    entity_id_field: str,
    entity_id: str,
    risk_profile: str,
    reason: str,
) -> dict[str, Any]:
    db = _get_db()
    current = db[entity_collection].find_one(
        {entity_id_field: entity_id},
        {"_id": 0, "risk_profile": 1},
    )
    previous = current.get("risk_profile") if current else None
    result = db[entity_collection].update_one(
        {entity_id_field: entity_id},
        {
            "$set": {
                "risk_profile": risk_profile,
                "_risk_update": {
                    "previous_profile": previous,
                    "new_profile": risk_profile,
                    "reason": reason,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": "reactive-intelligence",
                },
            }
        },
    )
    return {
        "ok": True,
        "matched": result.matched_count,
        "modified": result.modified_count,
    }


@router.skill()
def log_reaction(event: dict[str, Any]) -> dict[str, Any]:
    db = _get_db()
    payload = dict(event)
    payload["timestamp"] = datetime.now(timezone.utc)
    payload["agent"] = "reactive-intelligence"
    db["reaction_timeline"].insert_one(payload)
    return {"ok": True}


@router.skill()
def find_counterparty_context(
    counterparty_id: str,
    entity_collection: str,
    entity_id_field: str,
    document_collection: str,
    entity_lookup_field: str,
    limit: int = 20,
) -> dict[str, Any]:
    db = _get_db()
    entity = db[entity_collection].find_one(
        {entity_id_field: counterparty_id},
        {"_id": 0},
    )
    recent_documents = list(
        db[document_collection]
        .find({entity_lookup_field: counterparty_id}, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .limit(int(limit))
    )
    return {
        "ok": True,
        "entity": _serialize(entity) if entity is not None else None,
        "recent_documents": _serialize(recent_documents),
        "document_count": len(recent_documents),
    }


@router.skill()
def find_recent_high_risk(
    collection: str,
    min_risk_score: float = 0.6,
    hours_window: int = 48,
    limit: int = 20,
) -> dict[str, Any]:
    db = _get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(hours_window))
    query: dict[str, Any] = {
        "_intelligence.risk_score": {"$gte": float(min_risk_score)},
        "_intelligence.analyzed_at": {"$gte": cutoff},
    }
    docs = list(
        db[collection]
        .find(query, {"_id": 0})
        .sort("_intelligence.risk_score", DESCENDING)
        .limit(int(limit))
    )
    return {"ok": True, "count": len(docs), "documents": _serialize(docs)}


@router.skill()
def get_timeline(limit: int = 20, _: bool = True) -> dict[str, Any]:
    db = _get_db()
    events = list(
        db["reaction_timeline"]
        .find({}, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .limit(int(limit))
    )
    return {"ok": True, "count": len(events), "events": _serialize(events)}
