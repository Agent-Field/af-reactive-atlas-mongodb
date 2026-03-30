#!/usr/bin/env python3
"""Reactive Atlas domain demo runner.

Usage:
    python3 demo.py list
    python3 demo.py finance clean
    python3 demo.py finance all
    python3 demo.py finance reset
    python3 demo.py finance status
    python3 demo.py finance custom --amount 50000 --country KY --type wire_transfer --narrative "Consulting fees"
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DOMAINS_DIR = BASE_DIR / "domains"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing required environment variable: {name}")
        sys.exit(1)
    return value


def get_db():
    mongodb_uri = require_env("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "reactive_intelligence")
    return MongoClient(mongodb_uri)[db_name]


def get_agentfield_url() -> str:
    return os.getenv("AGENTFIELD_URL", "http://localhost:8092").rstrip("/")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def list_domains() -> list[str]:
    if not DOMAINS_DIR.exists():
        return []
    domains = []
    for entry in DOMAINS_DIR.iterdir():
        if (
            entry.is_dir()
            and (entry / "config.json").exists()
            and (entry / "scenarios.json").exists()
        ):
            domains.append(entry.name)
    return sorted(domains)


def load_domain_files(domain: str) -> tuple[dict[str, Any], dict[str, Any]]:
    domain_dir = DOMAINS_DIR / domain
    if not domain_dir.exists():
        raise SystemExit(f"Unknown domain '{domain}'. Run `python3 demo.py list`.")
    config_path = domain_dir / "config.json"
    scenarios_path = domain_dir / "scenarios.json"
    if not config_path.exists() or not scenarios_path.exists():
        raise SystemExit(f"Domain '{domain}' is missing config.json or scenarios.json")
    return load_json(config_path), load_json(scenarios_path)


def print_ui_urls():
    print(f"  AgentField UI: {get_agentfield_url()}")
    print("  Atlas UI:      https://cloud.mongodb.com")


def new_document_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{timestamp}_{uuid4().hex[:8]}"


def _resolve_value(value: Any, id_prefix: str) -> Any:
    if isinstance(value, str):
        if value == "__AUTO__":
            return new_document_id(id_prefix)
        if value == "__NOW__":
            return datetime.now(timezone.utc)
        return value
    if isinstance(value, dict):
        if "random" in value:
            low, high = value["random"]
            return round(random.uniform(float(low), float(high)), 2)
        if "choice" in value:
            options = value["choice"]
            return random.choice(options)
        return {k: _resolve_value(v, id_prefix) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(v, id_prefix) for v in value]
    return value


def build_documents_for_scenario(
    domain: str,
    config: dict[str, Any],
    scenario: dict[str, Any],
) -> list[dict[str, Any]]:
    id_prefix = f"{domain[:5]}_doc"
    docs = []
    for template in scenario.get("documents", []):
        docs.append(_resolve_value(template, id_prefix))

    doc_id_field = config.get("document_id_field")
    for doc in docs:
        if doc_id_field and not doc.get(doc_id_field):
            doc[doc_id_field] = new_document_id(id_prefix)
        if not doc.get("timestamp"):
            doc["timestamp"] = datetime.now(timezone.utc)
    return docs


def wait_for_enrichment(db, collection: str, id_field: str, document_ids: list[str]):
    poll_seconds = 3
    timeout_seconds = max(30, len(document_ids) * 15)
    spinner = "|/-\\"
    start = time.time()
    tick = 0

    while True:
        elapsed = int(time.time() - start)
        enriched = db[collection].count_documents(
            {
                id_field: {"$in": document_ids},
                "_intelligence": {"$exists": True},
            }
        )
        spin = spinner[tick % len(spinner)]
        sys.stdout.write(
            f"\r  {spin} waiting for enrichment {enriched}/{len(document_ids)} elapsed {elapsed}s"
        )
        sys.stdout.flush()

        if enriched == len(document_ids):
            print("\r  done: all documents enriched" + " " * 30)
            return
        if elapsed >= timeout_seconds:
            print("\r  timeout reached before all documents were enriched" + " " * 10)
            return

        tick += 1
        time.sleep(poll_seconds)


def trigger_processing(
    document: dict[str, Any],
    collection: str,
    domain: str,
) -> str:
    payload_doc = {k: v for k, v in document.items() if k != "_id"}
    if isinstance(payload_doc.get("timestamp"), datetime):
        payload_doc["timestamp"] = payload_doc["timestamp"].isoformat()

    response = httpx.post(
        f"{get_agentfield_url()}/api/v1/execute/async/reactive-intelligence.process_document",
        json={
            "input": {
                "document": payload_doc,
                "collection": collection,
                "domain": domain,
            }
        },
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("execution_id", "?")


def show_results(db, config: dict[str, Any], documents: list[dict[str, Any]]) -> None:
    collection = config["document_collection"]
    id_field = config["document_id_field"]

    for input_doc in documents:
        doc = db[collection].find_one(
            {id_field: input_doc[id_field]},
            {"_id": 0},
        )
        intelligence = doc.get("_intelligence") if doc else None
        if not intelligence:
            print(f"  pending {input_doc[id_field]}")
            continue

        amount = doc.get("amount")
        # Support both finance (geolocation.country) and ecommerce (shipping_address.country)
        geo = doc.get("geolocation") or doc.get("shipping_address") or {}
        country = geo.get("country", "??") if isinstance(geo, dict) else "??"
        amount_label = (
            f"${amount:,.2f}" if isinstance(amount, (int, float)) else str(amount)
        )
        print(f"  {doc[id_field]} amount={amount_label} country={country}")
        print(
            f"    risk={float(intelligence.get('risk_score', 0)):.2f} category={intelligence.get('risk_category', '?')} pattern={intelligence.get('pattern_match', 'none')}"
        )
        flags = intelligence.get("flags", [])
        if flags:
            print(f"    flags={', '.join(flags)}")
        summary = intelligence.get("summary", "")
        if summary:
            print(f"    summary={summary[:140]}{'...' if len(summary) > 140 else ''}")


def inject_and_process(
    db,
    domain: str,
    config: dict[str, Any],
    scenario_name: str,
    scenario_info: dict[str, Any],
    documents: list[dict[str, Any]],
) -> None:
    collection = config["document_collection"]
    id_field = config["document_id_field"]

    print(f"\n{'=' * 60}")
    print(f"  Domain: {domain}")
    print(f"  Scenario: {scenario_info.get('title', scenario_name)}")
    print(f"{'=' * 60}")
    print(f"  {scenario_info.get('description', '')}\n")

    for doc in documents:
        db[collection].insert_one(doc.copy())
        geo = doc.get("geolocation") or doc.get("shipping_address") or {}
        country = geo.get("country", "??") if isinstance(geo, dict) else "??"
        amount = doc.get("amount")
        amount_label = (
            f"${amount:,.2f}" if isinstance(amount, (int, float)) else str(amount)
        )
        doc_type = doc.get("type") or doc.get("shipping_method") or "?"
        print(
            f"  inserted {doc[id_field]} amount={amount_label} type={doc_type} country={country}"
        )

    execution_ids = []
    print("\n  submitting to AgentField process_document endpoint...")
    for doc in documents:
        try:
            execution_id = trigger_processing(doc, collection, domain)
            execution_ids.append(execution_id)
            print(f"    ok {doc[id_field]} execution={execution_id}")
        except Exception as exc:
            print(f"    failed {doc[id_field]} error={exc}")

    print("\n  waiting for AI enrichment...")
    wait_for_enrichment(db, collection, id_field, [d[id_field] for d in documents])

    print("\n  results")
    show_results(db, config, documents)

    entity_collection = config["entity_collection"]
    entity_id_field = config["entity_id_field"]
    cascaded = list(
        db[entity_collection].find(
            {"_risk_update": {"$exists": True}},
            {
                "_id": 0,
                entity_id_field: 1,
                "account_name": 1,
                "risk_profile": 1,
                "_risk_update.reason": 1,
            },
        )
    )
    if cascaded:
        print(f"\n  cascade updates ({len(cascaded)} entities)")
        for entity in cascaded:
            print(
                f"    {entity.get(entity_id_field)} {entity.get('account_name', '')} risk={entity.get('risk_profile', '?')}"
            )

    timeline = list(
        db["reaction_timeline"].find({}, {"_id": 0}).sort("timestamp", -1).limit(8)
    )
    if timeline:
        print(f"\n  reaction_timeline ({len(timeline)} latest)")
        for event in timeline:
            ts = event.get("timestamp")
            ts_label = (
                ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else "--:--:--"
            )
            print(
                f"    {ts_label} {event.get('trigger_type', '')} {event.get('document_id', '')} risk={event.get('risk_score', '?')}"
            )

    watch_items = scenario_info.get("watch", [])
    if watch_items:
        print("\n  what to look for")
        for item in watch_items:
            print(f"    - {item}")

    if execution_ids:
        print("\n  execution links")
        for execution_id in execution_ids:
            print(f"    {get_agentfield_url()}/api/v1/executions/{execution_id}")

    print()
    print_ui_urls()
    print()


def reset_domain_data(db, config: dict[str, Any]) -> None:
    collection = config["document_collection"]
    id_field = config["document_id_field"]
    context_loading = config.get("context_loading", {})

    print("\nresetting demo data...")
    db[collection].drop()
    db["reaction_timeline"].drop()
    db[config["entity_collection"]].update_many({}, {"$unset": {"_risk_update": ""}})

    db[collection].create_index(id_field, unique=True)
    if context_loading.get("entity_lookup_field"):
        db[collection].create_index(context_loading["entity_lookup_field"])
    if context_loading.get("counterparty_field"):
        db[collection].create_index(context_loading["counterparty_field"])
    db[collection].create_index("status")
    db[collection].create_index("timestamp")
    db[collection].create_index(
        [("_intelligence.risk_score", -1)],
        partialFilterExpression={"_intelligence": {"$exists": True}},
    )
    db["reaction_timeline"].create_index("timestamp")
    print("reset complete. base data preserved.\n")


def status(db, domain: str, config: dict[str, Any]) -> None:
    collection = config["document_collection"]
    threshold = float(config.get("cascade_config", {}).get("risk_threshold", 0.7))
    total = db[collection].count_documents({})
    enriched = db[collection].count_documents({"_intelligence": {"$exists": True}})
    high_risk = db[collection].count_documents(
        {"_intelligence.risk_score": {"$gte": threshold}}
    )
    cascaded = db[config["entity_collection"]].count_documents(
        {"_risk_update": {"$exists": True}}
    )
    reactions = db["reaction_timeline"].count_documents({"domain": domain})

    print(f"\nreactive atlas status ({domain})")
    print(f"  documents:          {total}")
    print(f"  enriched:           {enriched}/{total}")
    print(f"  high risk >= {threshold}: {high_risk}")
    print(f"  cascaded entities:  {cascaded}")
    print(f"  timeline events:    {reactions}\n")


def build_custom_document(
    args,
    config: dict[str, Any],
    scenarios: dict[str, Any],
) -> dict[str, Any]:
    defaults = scenarios.get("custom_template", {})
    context_loading = config.get("context_loading", {})
    entity_field = context_loading.get(
        "entity_lookup_field", config.get("entity_id_field")
    )
    counterparty_field = context_loading.get("counterparty_field")
    id_field = config.get("document_id_field")

    doc = dict(defaults)
    if id_field:
        doc[id_field] = new_document_id(f"{args.domain[:5]}_custom")
    if entity_field:
        doc[entity_field] = args.account_id or defaults.get(entity_field)
    if counterparty_field:
        doc[counterparty_field] = args.counterparty_id or defaults.get(
            counterparty_field
        )

    if args.amount is not None:
        doc["amount"] = round(args.amount, 2)
    if args.currency:
        doc["currency"] = args.currency
    if args.doc_type:
        doc["type"] = args.doc_type
    if args.channel:
        doc["channel"] = args.channel
    if args.narrative:
        doc["narrative"] = args.narrative
    if args.status:
        doc["status"] = args.status

    raw_geo = doc.get("geolocation")
    geolocation: dict[str, object] = dict(raw_geo) if isinstance(raw_geo, dict) else {}
    if args.country:
        geolocation["country"] = args.country
    if args.city:
        geolocation["city"] = args.city
    if geolocation:
        doc["geolocation"] = geolocation

    doc["timestamp"] = datetime.now(timezone.utc)
    return doc


def show_domain_list():
    domains = list_domains()
    if not domains:
        print("No domains found under domains/")
        return

    print("Available domains and scenarios:\n")
    for domain in domains:
        _, scenarios = load_domain_files(domain)
        order = scenarios.get("order", [])
        print(f"- {domain}: {', '.join(order)}")


def parse_args():
    parser = argparse.ArgumentParser(description="Reactive Atlas demo runner")
    parser.add_argument("domain", help="Domain name, or 'list'")
    parser.add_argument("command", nargs="?", help="Scenario name or command")

    parser.add_argument("--amount", type=float)
    parser.add_argument("--country")
    parser.add_argument("--type", dest="doc_type")
    parser.add_argument("--narrative")
    parser.add_argument("--account-id")
    parser.add_argument("--counterparty-id")
    parser.add_argument("--currency")
    parser.add_argument("--channel")
    parser.add_argument("--city")
    parser.add_argument("--status")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.domain == "list":
        show_domain_list()
        return

    if not args.command:
        raise SystemExit("Command required. Example: python3 demo.py finance clean")

    config, scenarios_doc = load_domain_files(args.domain)
    scenario_order = scenarios_doc.get("order", [])
    scenario_map = scenarios_doc.get("scenarios", {})

    db = get_db()

    if args.command == "reset":
        reset_domain_data(db, config)
        return
    if args.command == "status":
        status(db, args.domain, config)
        return
    if args.command == "all":
        reset_domain_data(db, config)
        for scenario_name in scenario_order:
            scenario_info = scenario_map.get(scenario_name, {})
            documents = build_documents_for_scenario(args.domain, config, scenario_info)
            inject_and_process(
                db,
                args.domain,
                config,
                scenario_name,
                scenario_info,
                documents,
            )
        return
    if args.command == "custom":
        custom_doc = build_custom_document(args, config, scenarios_doc)
        inject_and_process(
            db,
            args.domain,
            config,
            "custom",
            {
                "title": "Custom Document",
                "description": "One user-defined document injected with custom parameters.",
                "watch": [
                    "Confirm _intelligence appears on the inserted document.",
                    "Review risk score, pattern match, and flags.",
                ],
            },
            [custom_doc],
        )
        return

    if args.command not in scenario_map:
        supported = scenario_order + ["all", "custom", "reset", "status"]
        raise SystemExit(
            f"Unsupported command '{args.command}' for domain '{args.domain}'. "
            f"Supported: {', '.join(supported)}"
        )

    scenario_info = scenario_map[args.command]
    documents = build_documents_for_scenario(args.domain, config, scenario_info)
    inject_and_process(
        db,
        args.domain,
        config,
        args.command,
        scenario_info,
        documents,
    )


if __name__ == "__main__":
    main()
