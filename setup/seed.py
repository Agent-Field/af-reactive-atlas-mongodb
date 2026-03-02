import os
import random
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27019")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "reactive_intelligence")

random.seed(42)


COUNTRIES = ["US", "GB", "SG", "HK", "CH", "AE", "KY", "PA", "DE", "JP"]
HIGH_RISK_COUNTRIES = ["KY", "PA"]
CITIES = {
    "US": ["New York", "Chicago", "Miami", "San Francisco", "Houston"],
    "GB": ["London", "Manchester", "Edinburgh"],
    "SG": ["Singapore"],
    "HK": ["Hong Kong"],
    "CH": ["Zurich", "Geneva"],
    "AE": ["Dubai", "Abu Dhabi"],
    "KY": ["George Town"],
    "PA": ["Panama City"],
    "DE": ["Frankfurt", "Berlin"],
    "JP": ["Tokyo", "Osaka"],
}

ACCOUNT_TYPES = ["corporate", "individual", "institutional", "trust"]
KYC_STATUSES = ["verified", "pending_review", "expired", "enhanced_due_diligence"]
RISK_PROFILES = ["low", "medium", "high", "pep"]


Document = dict[str, object]


def generate_accounts() -> list[Document]:
    accounts: list[Document] = []

    corp_prefix = [
        "Global",
        "Meridian",
        "Summit",
        "Apex",
        "Harbor",
        "Orion",
        "Pinnacle",
        "Bluewater",
    ]
    corp_suffix = [
        "Holdings",
        "Trading",
        "Ventures",
        "Capital",
        "Industries",
        "Logistics",
        "Partners",
    ]
    inst_prefix = ["First", "Premier", "Continental", "Northbridge", "Crest", "Union"]
    inst_suffix = ["Bank", "Asset Management", "Securities", "Fund Services"]
    trust_prefix = ["Legacy", "Evergreen", "Crown", "Heritage", "Oakstone", "Sterling"]
    trust_suffix = ["Trust", "Family Office", "Foundation"]
    first_names = [
        "James",
        "Aisha",
        "Kenji",
        "Elena",
        "David",
        "Maya",
        "Liam",
        "Yuki",
        "Noah",
        "Sofia",
    ]
    last_names = [
        "Smith",
        "Tanaka",
        "Muller",
        "Patel",
        "Chen",
        "Dubois",
        "Khan",
        "Fischer",
        "Sato",
        "Wright",
    ]

    start = datetime(2021, 1, 1, tzinfo=timezone.utc)

    for i in range(1, 51):
        country = random.choice(COUNTRIES)
        city = random.choice(CITIES[country])
        account_type = random.choice(ACCOUNT_TYPES)

        if country in HIGH_RISK_COUNTRIES:
            kyc_status = random.choices(KYC_STATUSES, weights=[0.15, 0.3, 0.15, 0.4])[0]
            risk_profile = random.choices(
                RISK_PROFILES, weights=[0.05, 0.25, 0.45, 0.25]
            )[0]
        elif account_type == "trust":
            kyc_status = random.choices(KYC_STATUSES, weights=[0.45, 0.2, 0.1, 0.25])[0]
            risk_profile = random.choices(
                RISK_PROFILES, weights=[0.2, 0.4, 0.25, 0.15]
            )[0]
        else:
            kyc_status = random.choices(KYC_STATUSES, weights=[0.7, 0.15, 0.1, 0.05])[0]
            risk_profile = random.choices(
                RISK_PROFILES, weights=[0.55, 0.3, 0.12, 0.03]
            )[0]

        if account_type == "individual":
            account_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        elif account_type == "corporate":
            account_name = f"{random.choice(corp_prefix)} {random.choice(corp_suffix)} {random.choice(['Ltd', 'LLC', 'Group', 'PLC'])}"
        elif account_type == "institutional":
            account_name = f"{random.choice(inst_prefix)} {random.choice(inst_suffix)}"
        else:
            account_name = (
                f"{random.choice(trust_prefix)} {random.choice(trust_suffix)}"
            )

        onboarding_date = (start + timedelta(days=random.randint(0, 1800))).strftime(
            "%Y-%m-%d"
        )

        accounts.append(
            {
                "account_id": f"acc_{i:04d}",
                "account_name": account_name,
                "account_type": account_type,
                "country": country,
                "city": city,
                "kyc_status": kyc_status,
                "risk_profile": risk_profile,
                "onboarding_date": onboarding_date,
                "pep_flag": risk_profile == "pep",
                "beneficial_owner_verified": random.random() > 0.14,
            }
        )

    return accounts


def generate_policies() -> list[Document]:
    return [
        {
            "policy_id": "high-value-kyc",
            "collection": "transactions",
            "trigger": "insert",
            "intent": "Flag wire transfers over $100,000 from accounts with incomplete KYC verification for immediate compliance review",
            "action": "investigate",
            "active": True,
        },
        {
            "policy_id": "high-risk-jurisdiction",
            "collection": "transactions",
            "trigger": "insert",
            "intent": "Escalate any transaction where either the originator or counterparty is in a high-risk jurisdiction like Cayman Islands or Panama",
            "action": "escalate",
            "active": True,
        },
        {
            "policy_id": "structuring-detection",
            "collection": "transactions",
            "trigger": "insert",
            "intent": "Detect cash deposits or check deposits just below $10,000 that may indicate structuring to avoid CTR reporting thresholds",
            "action": "flag",
            "active": True,
        },
        {
            "policy_id": "velocity-alert",
            "collection": "transactions",
            "trigger": "insert",
            "intent": "Flag accounts that receive more than 3 transactions within a single hour as potential velocity anomalies",
            "action": "investigate",
            "active": True,
        },
        {
            "policy_id": "round-trip-monitor",
            "collection": "transactions",
            "trigger": "insert",
            "intent": "Identify transactions where funds appear to flow in a circular pattern back toward the originating account through intermediaries",
            "action": "escalate",
            "active": True,
        },
    ]


def generate_compliance_rules() -> list[Document]:
    return [
        {
            "rule_id": "BSA-001",
            "title": "Currency Transaction Report (CTR)",
            "jurisdiction": "US",
            "category": "reporting",
            "description": "Financial institutions must file a CTR for cash transactions over $10,000 in one business day. Aggregated transactions that exceed the threshold for the same customer must also be reported.",
        },
        {
            "rule_id": "BSA-002",
            "title": "Suspicious Activity Report (SAR)",
            "jurisdiction": "US",
            "category": "reporting",
            "description": "A SAR is required when activity appears to involve illicit funds, evasion of BSA controls, or no clear lawful purpose. Institutions should file promptly and document rationale for escalation.",
        },
        {
            "rule_id": "BSA-003",
            "title": "Structuring and Smurfing Detection",
            "jurisdiction": "US",
            "category": "detection",
            "description": "Structuring occurs when deposits are split to avoid CTR thresholds, often just below $10,000. Repeated sub-threshold cash patterns over short windows should trigger enhanced review.",
        },
        {
            "rule_id": "FATF-001",
            "title": "FATF Recommendation 10: CDD",
            "jurisdiction": "international",
            "category": "kyc",
            "description": "Institutions must identify and verify customers, beneficial owners, and expected account purpose. Higher-risk relationships require enhanced due diligence and stronger ongoing monitoring.",
        },
        {
            "rule_id": "FATF-002",
            "title": "FATF Recommendation 16: Wire Transfers",
            "jurisdiction": "international",
            "category": "wire",
            "description": "Wire transfers must carry complete originator and beneficiary details to support traceability. Missing or inconsistent payment fields should be treated as compliance exceptions.",
        },
        {
            "rule_id": "FATF-003",
            "title": "FATF High-Risk Jurisdictions Controls",
            "jurisdiction": "international",
            "category": "jurisdiction",
            "description": "Transactions connected to high-risk jurisdictions require enhanced due diligence and stricter monitoring. Control frameworks should apply additional scrutiny to source of funds and counterparties.",
        },
        {
            "rule_id": "EU-5AMLD",
            "title": "EU 5th Anti-Money Laundering Directive",
            "jurisdiction": "EU",
            "category": "aml",
            "description": "5AMLD strengthens transparency on beneficial ownership and broadens AML obligations. Institutions should maintain robust risk-based controls and reporting discipline across member states.",
        },
        {
            "rule_id": "MAS-626",
            "title": "MAS Notice 626",
            "jurisdiction": "SG",
            "category": "aml",
            "description": "MAS Notice 626 requires Singapore banks to apply customer due diligence, screening, and suspicious transaction reporting. Enhanced controls are required for high-risk customers and cross-border payments.",
        },
        {
            "rule_id": "OFAC-SDN",
            "title": "OFAC SDN Sanctions Screening",
            "jurisdiction": "US",
            "category": "sanctions",
            "description": "US persons are prohibited from dealings with SDN-listed individuals and entities. Screening should include names, aliases, beneficial owners, and payment references before and after execution.",
        },
        {
            "rule_id": "LAYER-001",
            "title": "Layering Pattern Detection",
            "jurisdiction": "international",
            "category": "detection",
            "description": "Layering is characterized by rapid sequential transfers across multiple accounts to obscure provenance. Amount reductions, short intervals, and cross-border hops are common indicators.",
        },
        {
            "rule_id": "SMURF-001",
            "title": "Smurfing Sequence Detection",
            "jurisdiction": "international",
            "category": "detection",
            "description": "Smurfing relies on repeated small deposits made below reportable limits. Institutions should aggregate activity by account, branch, and related parties to reveal hidden structuring.",
        },
        {
            "rule_id": "VELOC-001",
            "title": "Velocity Anomaly Detection",
            "jurisdiction": "international",
            "category": "detection",
            "description": "Dormant or low-activity accounts that suddenly generate bursts of high-value transfers represent elevated risk. Velocity checks should compare recent behavior against account baseline.",
        },
        {
            "rule_id": "ROUND-001",
            "title": "Round-Tripping Detection",
            "jurisdiction": "international",
            "category": "detection",
            "description": "Round-tripping occurs when funds return to the originator through intermediary entities. Circular paths with similar values and tight timing windows require investigation.",
        },
        {
            "rule_id": "PEP-001",
            "title": "PEP Enhanced Due Diligence",
            "jurisdiction": "international",
            "category": "kyc",
            "description": "Politically exposed persons require stronger onboarding and periodic review controls. Institutions should verify source of wealth, source of funds, and maintain heightened monitoring.",
        },
        {
            "rule_id": "TRAVEL-001",
            "title": "Wire Travel Rule Data Quality",
            "jurisdiction": "international",
            "category": "wire",
            "description": "Payment messages must preserve complete transfer metadata through intermediaries. Missing payer or beneficiary fields should be blocked or routed for manual review.",
        },
        {
            "rule_id": "CORR-001",
            "title": "Correspondent Banking Oversight",
            "jurisdiction": "international",
            "category": "kyc",
            "description": "Correspondent relationships should be risk-rated with documented AML control assessments. Nested relationship exposure and unusual payment corridors require additional scrutiny.",
        },
        {
            "rule_id": "BENOWN-001",
            "title": "Beneficial Ownership Transparency",
            "jurisdiction": "international",
            "category": "kyc",
            "description": "Legal-entity customers must disclose and verify ultimate beneficial owners and control persons. Opaque ownership chains should trigger enhanced due diligence.",
        },
        {
            "rule_id": "SHELL-001",
            "title": "Shell Entity Risk Indicators",
            "jurisdiction": "international",
            "category": "detection",
            "description": "Shell entities can be used to mask origin and destination of funds in laundering schemes. Indicators include minimal operational footprint and disproportionate transaction value.",
        },
        {
            "rule_id": "TBML-001",
            "title": "Trade-Based Money Laundering Signals",
            "jurisdiction": "international",
            "category": "detection",
            "description": "TBML uses trade documents and pricing manipulation to move value illicitly. Over- or under-invoicing and inconsistent shipment patterns are common red flags.",
        },
        {
            "rule_id": "SANCTION-001",
            "title": "Cross-Border Sanctions Escalation",
            "jurisdiction": "international",
            "category": "sanctions",
            "description": "Cross-border transfers involving sanctioned regions or restricted sectors require immediate escalation. Screening logic should evaluate counterparty, ownership, and narrative context together.",
        },
    ]


def generate_agent_metrics() -> list[Document]:
    metrics: list[Document] = []
    base_date = datetime.now(timezone.utc) - timedelta(days=29)

    start_detection = 0.12
    end_detection = 0.06
    start_conf = 0.74
    end_conf = 0.92

    for day in range(30):
        progress = day / 29
        detection_rate = (
            start_detection
            + (end_detection - start_detection) * progress
            + random.uniform(-0.006, 0.006)
        )
        confidence = (
            start_conf
            + (end_conf - start_conf) * progress
            + random.uniform(-0.012, 0.012)
        )

        metrics.append(
            {
                "timestamp": base_date + timedelta(days=day),
                "metric_type": "daily_summary",
                "detection_rate": round(min(0.15, max(0.05, detection_rate)), 4),
                "confidence": round(min(0.95, max(0.70, confidence)), 4),
                "transactions_analyzed": random.randint(100, 300),
                "alerts_generated": random.randint(2, 20),
                "elapsed_seconds": round(random.uniform(15.0, 45.0), 2),
            }
        )

    return metrics


def seed_database():
    print(f"Connecting to MongoDB: {MONGODB_URI[:40]}...")
    client: MongoClient[Document] = MongoClient(MONGODB_URI)
    db: Database[Document] = client[MONGODB_DATABASE]

    accounts_coll: Collection[Document] = db["accounts"]
    policies_coll: Collection[Document] = db["policies"]
    compliance_rules_coll: Collection[Document] = db["compliance_rules"]
    reaction_timeline_coll: Collection[Document] = db["reaction_timeline"]
    agent_metrics_coll: Collection[Document] = db["agent_metrics"]
    transactions_coll: Collection[Document] = db["transactions"]

    accounts = generate_accounts()
    policies = generate_policies()
    compliance_rules = generate_compliance_rules()
    agent_metrics = generate_agent_metrics()

    print("Generating demo data...")
    print(f"  Accounts: {len(accounts)}")
    print(f"  Policies: {len(policies)}")
    print(f"  Compliance rules: {len(compliance_rules)}")
    print(f"  Agent metrics: {len(agent_metrics)} (30-day history)")

    print("\nDropping existing collections...")
    for coll in [
        "transactions",
        "accounts",
        "policies",
        "compliance_rules",
        "reaction_timeline",
        "agent_state",
        "agent_metrics",
    ]:
        db[coll].drop()

    print("\nCreating time series collection: agent_metrics...")
    try:
        _ = db.create_collection(
            "agent_metrics",
            timeseries={
                "timeField": "timestamp",
                "metaField": "metric_type",
                "granularity": "minutes",
            },
        )
    except Exception as exc:
        print(f"  Note: {exc}")

    print("\nInserting base data...")
    _ = accounts_coll.insert_many(accounts)
    _ = policies_coll.insert_many(policies)
    _ = compliance_rules_coll.insert_many(compliance_rules)
    _ = agent_metrics_coll.insert_many(agent_metrics)

    print("\nCreating indexes...")
    _ = accounts_coll.create_index("account_id", unique=True)
    _ = policies_coll.create_index("policy_id", unique=True)
    _ = compliance_rules_coll.create_index("rule_id", unique=True)
    _ = compliance_rules_coll.create_index([("title", "text"), ("description", "text")])
    _ = reaction_timeline_coll.create_index("timestamp")

    _ = transactions_coll.create_index("transaction_id", unique=True)
    _ = transactions_coll.create_index("account_id")
    _ = transactions_coll.create_index("counterparty_id")
    _ = transactions_coll.create_index("status")
    _ = transactions_coll.create_index("timestamp")
    _ = transactions_coll.create_index(
        [("_intelligence.risk_score", -1)],
        partialFilterExpression={"_intelligence": {"$exists": True}},
    )

    print("\n=== Seed Complete ===")
    print(f"Database: {MONGODB_DATABASE}")
    print("Collections: transactions, accounts, policies, compliance_rules,")
    print("             reaction_timeline, agent_state, agent_metrics")
    print("Time series: agent_metrics (30-day history)")

    print("\nVerification:")
    for coll in ["accounts", "policies", "compliance_rules", "agent_metrics"]:
        count = db[coll].count_documents({})
        print(f"  {coll}: {count} documents")

    client.close()
    print("\nDone!")


if __name__ == "__main__":
    seed_database()
