#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pymongo import MongoClient


BASE_DIR = Path(__file__).resolve().parent.parent
DOMAINS_DIR = BASE_DIR / "domains"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def list_available_domains() -> list[str]:
    if not DOMAINS_DIR.exists():
        return []
    domains: list[str] = []
    for entry in DOMAINS_DIR.iterdir():
        if not entry.is_dir():
            continue
        required = [
            entry / "config.json",
            entry / "entities.json",
            entry / "rules.json",
            entry / "policies.json",
        ]
        if all(p.exists() for p in required):
            domains.append(entry.name)
    return sorted(domains)


def create_indexes(
    db,
    config: dict[str, Any],
    entities: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> None:
    document_collection = config["document_collection"]
    document_id_field = config["document_id_field"]
    entity_collection = config["entity_collection"]
    entity_id_field = config["entity_id_field"]
    rules_collection = config["rules_collection"]
    context_loading = config.get("context_loading", {})

    db["domain_config"].create_index("domain", unique=True)
    db["policies"].create_index([("domain", 1), ("policy_id", 1)], unique=True)
    db["reaction_timeline"].create_index("timestamp")

    db[entity_collection].create_index(entity_id_field, unique=True)
    if entities and "risk_profile" in entities[0]:
        db[entity_collection].create_index("risk_profile")

    if rules and "rule_id" in rules[0]:
        db[rules_collection].create_index("rule_id", unique=True)
    db[rules_collection].create_index([("title", "text"), ("description", "text")])

    db[document_collection].create_index(document_id_field, unique=True)
    if context_loading.get("entity_lookup_field"):
        db[document_collection].create_index(context_loading["entity_lookup_field"])
    if context_loading.get("counterparty_field"):
        db[document_collection].create_index(context_loading["counterparty_field"])
    db[document_collection].create_index("status")
    db[document_collection].create_index("timestamp")
    db[document_collection].create_index(
        [("_intelligence.risk_score", -1)],
        partialFilterExpression={"_intelligence": {"$exists": True}},
    )


def seed_domain(db, domain: str) -> None:
    domain_dir = DOMAINS_DIR / domain
    config = load_json(domain_dir / "config.json")
    entities_raw = load_json(domain_dir / "entities.json")
    rules = load_json(domain_dir / "rules.json")
    policies = load_json(domain_dir / "policies.json")

    entity_collection = config["entity_collection"]
    entity_id_field = config["entity_id_field"]

    # entities.json can be a flat list or a dict keyed by collection name
    if isinstance(entities_raw, list):
        entities = entities_raw
    elif isinstance(entities_raw, dict):
        entities = entities_raw.get(entity_collection, [])
    else:
        entities = []
    rules_collection = config["rules_collection"]

    print(f"\nSeeding domain: {domain}")
    print("Upserting config, entities, rules, and policies...")

    config["domain"] = domain
    db["domain_config"].update_one(
        {"domain": domain},
        {"$set": config},
        upsert=True,
    )

    for entity in entities:
        db[entity_collection].update_one(
            {entity_id_field: entity[entity_id_field]},
            {"$setOnInsert": entity},
            upsert=True,
        )

    for rule in rules:
        db[rules_collection].update_one(
            {"rule_id": rule["rule_id"]},
            {"$set": rule},
            upsert=True,
        )

    normalized_policies = []
    for policy in policies:
        item = dict(policy)
        item["domain"] = domain
        normalized_policies.append(item)
    for policy in normalized_policies:
        db["policies"].update_one(
            {"domain": domain, "policy_id": policy["policy_id"]},
            {"$set": policy},
            upsert=True,
        )

    create_indexes(db, config, entities, rules)

    print(
        f"Seeded {domain}: entities={len(entities)} rules={len(rules)} policies={len(normalized_policies)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Reactive Atlas domain data")
    parser.add_argument(
        "domain",
        nargs="?",
        default="all",
        help="Domain name to seed, or 'all'",
    )
    args = parser.parse_args()

    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27019")
    mongodb_database = os.getenv("MONGODB_DATABASE", "reactive_intelligence")

    available = list_available_domains()
    if not available:
        raise SystemExit(f"No seedable domains found in {DOMAINS_DIR}")

    if args.domain == "all":
        targets = available
    else:
        if args.domain not in available:
            raise SystemExit(
                f"Unknown domain '{args.domain}'. Available: {', '.join(available)}"
            )
        targets = [args.domain]

    print(f"Connecting to MongoDB: {mongodb_database}")
    client = MongoClient(mongodb_uri)
    db = client[mongodb_database]

    try:
        db["policies"].drop_index("policy_id_1")
    except Exception:
        pass

    for domain in targets:
        seed_domain(db, domain)

    print(f"\nSeed complete for: {', '.join(targets)}")
    client.close()


if __name__ == "__main__":
    main()
