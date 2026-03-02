import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, MongoClient

from .router import router


_client: MongoClient | None = None
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
def enrich_document(collection: str, document_id: str, intelligence: dict) -> dict:
    db = _get_db()
    enrichment = dict(intelligence)
    enrichment["analyzed_at"] = datetime.now(timezone.utc)
    enrichment["version"] = 1

    existing = db[collection].find_one({"transaction_id": document_id})
    if existing and existing.get("_intelligence"):
        enrichment["version"] = existing["_intelligence"].get("version", 0) + 1

    db[collection].update_one(
        {"transaction_id": document_id},
        {"$set": {"_intelligence": enrichment}},
    )

    return {"ok": True, "document_id": document_id, "enriched": True}


@router.skill()
def load_active_policies(_: bool = True) -> dict:
    db = _get_db()
    policies = list(db["policies"].find({"active": True}, {"_id": 0}))
    return {"ok": True, "count": len(policies), "policies": policies}


@router.skill()
def lookup_account(account_id: str) -> dict:
    db = _get_db()
    account = db["accounts"].find_one({"account_id": account_id}, {"_id": 0})
    return {"ok": True, "found": account is not None, "account": account}


@router.skill()
def find_related_transactions(account_id: str, limit: int = 50) -> dict:
    db = _get_db()
    query = {
        "$or": [
            {"account_id": account_id},
            {"counterparty_id": account_id},
        ]
    }
    docs = list(
        db["transactions"]
        .find(query, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .limit(int(limit))
    )
    return {"ok": True, "count": len(docs), "transactions": _serialize(docs)}


@router.skill()
def load_compliance_rules(query: str, k: int = 5) -> dict:
    db = _get_db()
    docs = list(
        db["compliance_rules"]
        .find(
            {"$text": {"$search": query}},
            {"_id": 0, "score": {"$meta": "textScore"}},
        )
        .sort([("score", {"$meta": "textScore"})])
        .limit(int(k))
    )
    return {"ok": True, "count": len(docs), "rules": docs}


@router.skill()
def update_account_risk(account_id: str, risk_profile: str, reason: str) -> dict:
    db = _get_db()
    result = db["accounts"].update_one(
        {"account_id": account_id},
        {
            "$set": {
                "risk_profile": risk_profile,
                "_risk_update": {
                    "previous_profile": None,
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
def log_reaction(event: dict) -> dict:
    db = _get_db()
    payload = dict(event)
    payload["timestamp"] = datetime.now(timezone.utc)
    payload["agent"] = "reactive-intelligence"
    db["reaction_timeline"].insert_one(payload)
    return {"ok": True}


@router.skill()
def get_timeline(limit: int = 20) -> dict:
    db = _get_db()
    events = list(
        db["reaction_timeline"]
        .find({}, {"_id": 0})
        .sort("timestamp", DESCENDING)
        .limit(int(limit))
    )
    return {"ok": True, "count": len(events), "events": _serialize(events)}
