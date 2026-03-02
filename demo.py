#!/usr/bin/env python3
"""Reactive Atlas demo runner.

Usage:
    python3 demo.py clean
    python3 demo.py structuring
    python3 demo.py round-trip
    python3 demo.py layering
    python3 demo.py big-one
    python3 demo.py custom --amount 50000 --country KY --type wire_transfer --narrative "Consulting fees"
    python3 demo.py all
    python3 demo.py reset
    python3 demo.py status
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from pymongo import MongoClient

SCENARIO_ORDER = ["clean", "structuring", "round-trip", "layering", "big-one"]
SCENARIO_INFO = {
    "clean": {
        "title": "Clean Business Transactions",
        "description": "Three normal transactions with realistic narratives and amounts.",
        "watch": [
            "Risk scores should stay low for all three transactions.",
            "Pattern match should stay at none.",
            "No compliance flags should be present.",
        ],
    },
    "structuring": {
        "title": "Structuring Pattern",
        "description": "Five cash deposits from one account, all just under the $10K CTR threshold.",
        "watch": [
            "Pattern detection should identify structuring or smurfing behavior.",
            "Risk should climb as repeated below-threshold deposits accumulate.",
            "Compliance flags should reference structuring related rules.",
        ],
    },
    "round-trip": {
        "title": "Round-Trip Flow",
        "description": "Three-hop circular transfer A->B->C->A with decreasing amounts.",
        "watch": [
            "Pattern detection should identify circular money flow.",
            "Narrative summary should mention round-tripping behavior.",
            "Related accounts may receive risk updates from cascade.",
        ],
    },
    "layering": {
        "title": "Layering Across Jurisdictions",
        "description": "Four SWIFT hops US->HK->KY->CH with slight value decay at each hop.",
        "watch": [
            "Pattern detection should identify layering behavior.",
            "High-risk jurisdiction rules should fire on the KY hop.",
            "Cascade can propagate risk to linked accounts and activity.",
        ],
    },
    "big-one": {
        "title": "Single High-Risk Wire",
        "description": "One large pending-review SWIFT wire from Cayman Islands.",
        "watch": [
            "Risk score should be elevated into high or critical territory.",
            "Compliance flags should include high-value and jurisdiction signals.",
            "Policies and cascade actions should be visible in reaction_timeline.",
        ],
    },
    "custom": {
        "title": "Custom Transaction",
        "description": "One user-defined transaction injected with custom parameters.",
        "watch": [
            "Confirm _intelligence appears on the inserted document.",
            "Review risk score, pattern match, and compliance flags.",
            "Check reaction_timeline for policy evaluation and cascade activity.",
        ],
    },
}

LEGIT_NARRATIVES = [
    "Invoice settlement for quarterly logistics services",
    "Enterprise software annual license renewal",
    "Regional office operating expense transfer",
    "Vendor payment for managed infrastructure support",
    "Professional services retainer payment",
    "Procurement payment for approved hardware order",
]

STRUCTURING_NARRATIVES = [
    "Cash deposit from daily branch activity",
    "Cash deposit for local operations",
    "Cash receipt settlement",
]

ROUND_TRIP_NARRATIVES = [
    "Investment allocation transfer",
    "Intercompany treasury adjustment",
    "Portfolio balancing transfer",
]

LAYERING_NARRATIVES = [
    "Cross-border settlement transfer",
    "Strategic reserve movement",
    "Liquidity routing transfer",
    "Offshore vehicle funding movement",
]


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


def new_transaction_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{timestamp}_{uuid4().hex[:8]}"


def random_amount(low: float, high: float) -> float:
    return round(random.uniform(low, high), 2)


def create_scenario_transactions(scenario_name: str):
    now = datetime.now(timezone.utc)

    if scenario_name == "clean":
        pairs = [
            ("acc_0005", "acc_0010"),
            ("acc_0018", "acc_0022"),
            ("acc_0033", "acc_0007"),
        ]
        currencies = ["USD", "EUR", "GBP"]
        geos = [("US", "Chicago"), ("DE", "Berlin"), ("GB", "London")]
        types = ["ach", "wire_transfer", "ach"]
        channels = ["online_banking", "api", "api"]
        txns = []
        for idx in range(3):
            txns.append(
                {
                    "transaction_id": new_transaction_id("txn_clean"),
                    "account_id": pairs[idx][0],
                    "counterparty_id": pairs[idx][1],
                    "amount": random_amount(1000, 20000),
                    "currency": currencies[idx],
                    "type": types[idx],
                    "channel": channels[idx],
                    "geolocation": {"country": geos[idx][0], "city": geos[idx][1]},
                    "narrative": random.choice(LEGIT_NARRATIVES),
                    "status": "completed",
                    "timestamp": now,
                }
            )
        return txns

    if scenario_name == "structuring":
        txns = []
        for _ in range(5):
            txns.append(
                {
                    "transaction_id": new_transaction_id("txn_struct"),
                    "account_id": "acc_0028",
                    "counterparty_id": "acc_0028",
                    "amount": random_amount(9100, 9950),
                    "currency": "USD",
                    "type": "cash_deposit",
                    "channel": "branch",
                    "geolocation": {"country": "US", "city": "Miami"},
                    "narrative": random.choice(STRUCTURING_NARRATIVES),
                    "status": "completed",
                    "timestamp": now,
                }
            )
        return txns

    if scenario_name == "round-trip":
        accounts = ["acc_0015", "acc_0025", "acc_0035", "acc_0015"]
        geos = [("CH", "Zurich"), ("HK", "Hong Kong"), ("SG", "Singapore")]
        current_amount = random_amount(120000, 220000)
        txns = []
        for idx in range(3):
            txns.append(
                {
                    "transaction_id": new_transaction_id("txn_round"),
                    "account_id": accounts[idx],
                    "counterparty_id": accounts[idx + 1],
                    "amount": round(current_amount, 2),
                    "currency": "USD",
                    "type": "wire_transfer",
                    "channel": "swift",
                    "geolocation": {"country": geos[idx][0], "city": geos[idx][1]},
                    "narrative": ROUND_TRIP_NARRATIVES[idx],
                    "status": "completed",
                    "timestamp": now,
                }
            )
            current_amount *= 1 - random.uniform(0.005, 0.02)
        return txns

    if scenario_name == "layering":
        accounts = ["acc_0003", "acc_0019", "acc_0038", "acc_0046", "acc_0009"]
        geos = [
            ("US", "New York"),
            ("HK", "Hong Kong"),
            ("KY", "George Town"),
            ("CH", "Geneva"),
        ]
        current_amount = random_amount(180000, 320000)
        txns = []
        for idx in range(4):
            txns.append(
                {
                    "transaction_id": new_transaction_id("txn_layer"),
                    "account_id": accounts[idx],
                    "counterparty_id": accounts[idx + 1],
                    "amount": round(current_amount, 2),
                    "currency": "USD",
                    "type": "wire_transfer",
                    "channel": "swift",
                    "geolocation": {"country": geos[idx][0], "city": geos[idx][1]},
                    "narrative": LAYERING_NARRATIVES[idx],
                    "status": "completed",
                    "timestamp": now,
                }
            )
            current_amount *= 1 - random.uniform(0.003, 0.015)
        return txns

    if scenario_name == "big-one":
        return [
            {
                "transaction_id": new_transaction_id("txn_big"),
                "account_id": "acc_0042",
                "counterparty_id": "acc_0049",
                "amount": random_amount(500000, 1200000),
                "currency": "USD",
                "type": "wire_transfer",
                "channel": "swift",
                "geolocation": {"country": "KY", "city": "George Town"},
                "narrative": "Consulting fees - offshore vehicle administration",
                "status": "pending_review",
                "timestamp": now,
            }
        ]

    raise ValueError(f"Unsupported scenario: {scenario_name}")


def wait_for_enrichment(db, transaction_ids):
    poll_seconds = 3
    timeout_seconds = max(30, len(transaction_ids) * 15)
    spinner = "|/-\\"
    start = time.time()
    tick = 0

    while True:
        elapsed = int(time.time() - start)
        enriched = db.transactions.count_documents(
            {
                "transaction_id": {"$in": transaction_ids},
                "_intelligence": {"$exists": True},
            }
        )
        spin = spinner[tick % len(spinner)]
        sys.stdout.write(
            f"\r  {spin} waiting for enrichment {enriched}/{len(transaction_ids)} elapsed {elapsed}s"
        )
        sys.stdout.flush()

        if enriched == len(transaction_ids):
            print("\r  done: all transactions enriched" + " " * 30)
            return
        if elapsed >= timeout_seconds:
            print("\r  timeout reached before all documents were enriched" + " " * 10)
            return

        tick += 1
        time.sleep(poll_seconds)


def print_ui_urls():
    print(f"  AgentField UI: {get_agentfield_url()}")
    print("  Atlas UI:      https://cloud.mongodb.com")


def trigger_processing(transaction):
    doc = {k: v for k, v in transaction.items() if k != "_id"}
    doc["timestamp"] = doc["timestamp"].isoformat()

    response = httpx.post(
        f"{get_agentfield_url()}/api/v1/execute/async/reactive-intelligence.process_document",
        json={"input": {"document": doc, "collection": "transactions"}},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("execution_id", "?")


def show_results(db, transactions):
    for txn in transactions:
        doc = db.transactions.find_one(
            {"transaction_id": txn["transaction_id"]},
            {
                "_id": 0,
                "transaction_id": 1,
                "amount": 1,
                "geolocation": 1,
                "_intelligence": 1,
            },
        )
        intel = doc.get("_intelligence") if doc else None
        if not intel:
            print(f"  pending {txn['transaction_id']}")
            continue

        print(
            f"  {doc['transaction_id']} amount=${doc['amount']:,.2f} country={doc.get('geolocation', {}).get('country', '??')}"
        )
        print(
            f"    risk={intel.get('risk_score', 0):.2f} category={intel.get('risk_category', '?')} pattern={intel.get('pattern_match', 'none')}"
        )
        flags = intel.get("compliance_flags", [])
        if flags:
            print(f"    flags={', '.join(flags)}")
        summary = intel.get("summary", "")
        if summary:
            print(f"    summary={summary[:140]}{'...' if len(summary) > 140 else ''}")


def inject_and_process(db, scenario_name, transactions=None):
    info = SCENARIO_INFO[scenario_name]
    txns = (
        transactions
        if transactions is not None
        else create_scenario_transactions(scenario_name)
    )

    print(f"\n{'=' * 60}")
    print(f"  Scenario: {info['title']}")
    print(f"{'=' * 60}")
    print(f"  {info['description']}\n")

    for txn in txns:
        db.transactions.insert_one(txn.copy())
        geo = txn.get("geolocation", {}) if isinstance(txn, dict) else {}
        country = geo.get("country", "??") if isinstance(geo, dict) else "??"
        print(
            f"  inserted {txn['transaction_id']} amount=${txn['amount']:,.2f} type={txn['type']} country={country}"
        )

    execution_ids = []
    print("\n  submitting to AgentField process_document endpoint...")
    for txn in txns:
        try:
            execution_id = trigger_processing(txn)
            execution_ids.append(execution_id)
            print(f"    ok {txn['transaction_id']} execution={execution_id}")
        except Exception as exc:
            print(f"    failed {txn['transaction_id']} error={exc}")

    print("\n  waiting for AI enrichment...")
    wait_for_enrichment(db, [txn["transaction_id"] for txn in txns])

    print("\n  results")
    show_results(db, txns)

    cascaded = list(
        db.accounts.find(
            {"_risk_update": {"$exists": True}},
            {
                "_id": 0,
                "account_id": 1,
                "account_name": 1,
                "risk_profile": 1,
                "_risk_update.reason": 1,
            },
        )
    )
    if cascaded:
        print(f"\n  cascade updates ({len(cascaded)} accounts)")
        for account in cascaded:
            print(
                f"    {account['account_id']} {account.get('account_name', '')} risk={account.get('risk_profile', '?')}"
            )

    timeline = list(
        db.reaction_timeline.find({}, {"_id": 0}).sort("timestamp", -1).limit(8)
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

    print("\n  what to look for")
    for item in info["watch"]:
        print(f"    - {item}")

    if execution_ids:
        print("\n  execution links")
        for execution_id in execution_ids:
            print(f"    {get_agentfield_url()}/api/v1/executions/{execution_id}")

    print()
    print_ui_urls()
    print()


def build_custom_transaction(args):
    return {
        "transaction_id": new_transaction_id("txn_custom"),
        "account_id": args.account_id,
        "counterparty_id": args.counterparty_id,
        "amount": round(args.amount, 2),
        "currency": args.currency,
        "type": args.txn_type,
        "channel": args.channel,
        "geolocation": {"country": args.country, "city": args.city},
        "narrative": args.narrative,
        "status": args.status,
        "timestamp": datetime.now(timezone.utc),
    }


def reset(db):
    print("\nresetting demo data...")
    db.transactions.drop()
    db.reaction_timeline.drop()
    db.accounts.update_many({}, {"$unset": {"_risk_update": ""}})
    db.transactions.create_index("transaction_id", unique=True)
    db.transactions.create_index("account_id")
    db.transactions.create_index("counterparty_id")
    db.transactions.create_index("status")
    db.transactions.create_index("timestamp")
    db.transactions.create_index(
        [("_intelligence.risk_score", -1)],
        partialFilterExpression={"_intelligence": {"$exists": True}},
    )
    db.reaction_timeline.create_index("timestamp")
    print("reset complete. base data preserved.\n")


def status(db):
    total = db.transactions.count_documents({})
    enriched = db.transactions.count_documents({"_intelligence": {"$exists": True}})
    high_risk = db.transactions.count_documents(
        {"_intelligence.risk_score": {"$gte": 0.7}}
    )
    cascaded = db.accounts.count_documents({"_risk_update": {"$exists": True}})
    reactions = db.reaction_timeline.count_documents({})

    print("\nreactive atlas status")
    print(f"  transactions:       {total}")
    print(f"  enriched:           {enriched}/{total}")
    print(f"  high risk >= 0.7:   {high_risk}")
    print(f"  cascaded accounts:  {cascaded}")
    print(f"  timeline events:    {reactions}\n")


def build_parser():
    parser = argparse.ArgumentParser(description="Reactive Atlas demo runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in SCENARIO_ORDER + ["all", "reset", "status"]:
        subparsers.add_parser(command)

    custom = subparsers.add_parser("custom")
    custom.add_argument("--amount", type=float, required=True)
    custom.add_argument("--country", required=True)
    custom.add_argument("--type", dest="txn_type", required=True)
    custom.add_argument("--narrative", required=True)
    custom.add_argument("--account-id", default="acc_0012")
    custom.add_argument("--counterparty-id", default="acc_0030")
    custom.add_argument("--currency", default="USD")
    custom.add_argument("--channel", default="api")
    custom.add_argument("--city", default="Unknown")
    custom.add_argument("--status", default="completed")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    db = get_db()

    if args.command == "reset":
        reset(db)
        return
    if args.command == "status":
        status(db)
        return
    if args.command == "all":
        reset(db)
        for name in SCENARIO_ORDER:
            inject_and_process(db, name)
        return
    if args.command == "custom":
        custom_txn = build_custom_transaction(args)
        inject_and_process(
            db,
            "custom",
            transactions=[custom_txn],
        )
        return

    inject_and_process(db, args.command)


if __name__ == "__main__":
    main()
