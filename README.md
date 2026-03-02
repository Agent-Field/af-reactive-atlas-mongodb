# Reactive Atlas

**Turn any MongoDB collection into an AI-powered intelligence layer.**

Atlas Triggers detect changes. [AgentField](https://github.com/Agent-Field/agentfield) adds the reasoning. Documents arrive raw and leave enriched — risk scores, pattern detection, policy decisions, all written back in place. No application code. No rule engines. No polling.

[![AgentField](https://img.shields.io/badge/Powered%20by-AgentField-6366f1?style=flat-square)](https://github.com/Agent-Field/agentfield)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-00ED64?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## See it in action

A cash deposit hits the `transactions` collection:

```json
{
  "transaction_id": "txn_20240315_a8f3",
  "account_id": "acc_0028",
  "amount": 9800,
  "type": "cash_deposit",
  "channel": "branch",
  "geolocation": { "country": "US", "city": "Miami" },
  "narrative": "Cash deposit from daily operations",
  "status": "completed"
}
```

10 seconds later, **the same document** in Atlas:

```json
{
  "transaction_id": "txn_20240315_a8f3",
  "account_id": "acc_0028",
  "amount": 9800,
  "type": "cash_deposit",
  "channel": "branch",
  "geolocation": { "country": "US", "city": "Miami" },
  "narrative": "Cash deposit from daily operations",
  "status": "completed",
  "_intelligence": {
    "risk_score": 0.82,
    "risk_category": "high",
    "pattern_match": "structuring",
    "flags": ["STRUCT-001", "THRESH-001", "VELOCITY-002"],
    "summary": "Cash deposit of $9,800 is just below the $10,000 CTR reporting threshold. Account acc_0028 has made 4 similar sub-threshold deposits within 48 hours totaling $38,400. Pattern is consistent with structuring to avoid BSA reporting requirements.",
    "analyzed_at": "2024-03-15T14:23:07Z",
    "version": 1
  }
}
```

No code wrote that. An Atlas Trigger fired, AgentField reasoned over the account's history, applied compliance rules, and enriched the document in place. The account's risk profile was updated. Four related transactions were flagged for re-analysis.

**The database initiated intelligence. The application did nothing.**

---

## Architecture

```mermaid
flowchart TD
    subgraph Atlas ["MongoDB Atlas"]
        C1["transactions"]
        C2["orders"]
        C3["any collection"]
        DC["domain_config"]
        RT["reaction_timeline"]
    end

    subgraph AF ["AgentField"]
        R["Reasoner: process_document"]
        S1["Load entity context"]
        S2["Retrieve domain rules"]
        S3["LLM structured reasoning"]
        S4["Evaluate policies"]
        S5["Cascade risk updates"]
    end

    C1 -- "Atlas Trigger" --> R
    C2 -- "Atlas Trigger" --> R
    C3 -. "Atlas Trigger" .-> R
    DC -- "config drives behavior" --> R
    R --> S1 --> S2 --> S3 --> S4 --> S5
    S3 -- "_intelligence" --> C1
    S3 -- "_intelligence" --> C2
    S5 -- "audit trail" --> RT
```

The architecture has three parts:

- **Atlas Triggers** fire on document insert and call AgentField over HTTPS. This is MongoDB's native change detection — no external poller, no cron, no queue.
- **AgentField** runs the reasoning agent. It loads a domain config from MongoDB that tells it which collection to watch, what entity to look up, which rules to apply, what prompt to use, and when to cascade. The agent is generic; the config makes it specific.
- **`_intelligence`** is written back into the source document. The original data is untouched. Intelligence is additive, versioned, and queryable — you can index on `_intelligence.risk_score` and build dashboards directly off enriched documents.

### What happens on every insert

1. **Atlas Trigger** fires and passes the full document to AgentField
2. **Domain resolution** — the collection name maps to a domain config document in MongoDB
3. **Context assembly** — entity profile, transaction history, and relevant rules are loaded in parallel
4. **LLM reasoning** — the domain-specific prompt, full context, and rule set produce a structured `DocumentIntelligence` judgment
5. **In-place enrichment** — `_intelligence` is written back to the source document
6. **Policy evaluation** — plain-English policies are checked against the enrichment (e.g., *"Flag wire transfers over $100K from accounts with incomplete KYC"*)
7. **Cascade** — if risk exceeds the threshold, linked entity profiles are updated and related unenriched documents are re-analyzed
8. **Audit trail** — every decision is logged to `reaction_timeline`

---

## Config is the product

All AI behavior lives in a single MongoDB document. This is the entire configuration for the finance domain:

```json
{
  "domain": "finance",
  "document_collection": "transactions",
  "document_id_field": "transaction_id",
  "entity_collection": "accounts",
  "entity_id_field": "account_id",
  "rules_collection": "compliance_rules",
  "context_loading": {
    "entity_lookup_field": "account_id",
    "counterparty_field": "counterparty_id",
    "history_match_fields": ["account_id", "counterparty_id"],
    "history_limit": 50
  },
  "cascade_config": {
    "risk_threshold": 0.7,
    "update_entities": true,
    "reenrich_related": true,
    "max_reenrich": 10
  },
  "analysis_prompt": "You are a financial crime analyst performing AML risk assessment..."
}
```

Every field controls behavior:
- **`document_collection`** + **`entity_collection`** — which collections to read from and write to
- **`context_loading`** — how to assemble context (which fields link documents to entities, how much history to load)
- **`cascade_config`** — when and how to propagate risk (threshold, whether to update entities, how many related docs to re-enrich)
- **`analysis_prompt`** — the domain-specific instructions the LLM follows
- **`rules_collection`** — which rules the AI reasons over (loaded via text search, not hardcoded)

Change the config document in MongoDB and the AI behavior changes immediately. No code. No redeploy. A compliance team can tune their AML thresholds. A fraud team can adjust cascade sensitivity. A new domain can be live in 30 minutes.

---

## Use cases

This pattern works anywhere documents arrive and need intelligent assessment. The engine is domain-agnostic — the config document makes it specific.

| Domain | Collection | What the AI does | Why rules engines fail |
|---|---|---|---|
| **Financial compliance** | `transactions` | AML pattern detection, structuring identification, counterparty risk propagation | Structuring is a *pattern* across transactions, not a property of one |
| **E-commerce fraud** | `orders` | Velocity abuse, synthetic identity signals, friendly fraud detection | Account takeover looks different every time; the *combination* of signals matters |
| **Healthcare triage** | `patient_intake` | Urgency scoring, drug interaction alerts, department routing | Urgency depends on the full patient context, not individual symptoms |
| **Content moderation** | `posts` | Toxicity scoring, policy violation detection, context-aware escalation | Sarcasm, cultural context, and evolving norms defeat keyword matching |
| **Cybersecurity** | `security_events` | Threat classification, anomaly scoring, lateral movement detection | Novel attack patterns aren't in the rule book yet |
| **Insurance claims** | `claims` | Fraud signal detection, claimant history cross-referencing, fast-track routing | Legitimate claims that *look* suspicious need judgment, not flags |
| **IoT / Telemetry** | `sensor_readings` | Anomaly detection, predictive maintenance triggers, fleet-wide correlation | "Anomalous" depends on the device's own baseline, not a global threshold |
| **Supply chain** | `shipments` | Delay risk scoring, vendor reliability assessment, route anomaly detection | Risk is contextual — same delay means different things for different routes |

The "Why rules engines fail" column is the point. Every domain above has been attempted with static rules, and every one hits the same wall: **context-dependent judgment doesn't reduce to if-else**. That's what the LLM provides.

### Shipped examples

This repo ships two fully worked domains you can run right now:

**[Finance — AML compliance](domains/finance/)**: 50 accounts, 20 compliance rules, 5 policies, 5 scenarios

```bash
python3 demo.py finance structuring    # 5 cash deposits just under $10K
python3 demo.py finance round-trip     # circular A->B->C->A transfer
python3 demo.py finance layering       # US->HK->KY->CH SWIFT chain
python3 demo.py finance big-one        # single $500K+ Cayman wire
python3 demo.py finance clean          # 3 normal transfers (baseline)
```

**[E-commerce — order fraud](domains/ecommerce/)**: 40 customers, 15 fraud rules, 5 policies, 5 scenarios

```bash
python3 demo.py ecommerce velocity-abuse       # 5 rapid orders, rotating addresses
python3 demo.py ecommerce synthetic-identity   # new accounts, mismatched signals
python3 demo.py ecommerce friendly-fraud       # high returns history + expensive items
python3 demo.py ecommerce high-value-mismatch  # cross-border electronics, new account
python3 demo.py ecommerce normal               # 3 legitimate orders (baseline)
```

Both run on the same agent, same skills, same reasoning loop. The only difference is the config document in MongoDB.

---

## Build your own domain

Adding a new domain requires **zero Python code changes**. The engine is fully config-driven.

```
domains/yourname/
  config.json        # What to watch, how to reason, when to cascade
  entities.json      # Seed entities (accounts, customers, devices, patients)
  rules.json         # Domain rules the AI reasons over
  policies.json      # Plain-English policies evaluated after enrichment
  scenarios.json     # Demo scenarios with document templates
```

```bash
python3 setup/seed.py yourname        # seed the domain
python3 demo.py yourname yourscenario # run a scenario
```

Add your collection to the Atlas Trigger's `domainMap` and you're live. The same trigger function handles all domains.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Python 3.10+
- [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) account (free M0 tier is sufficient)
- [OpenRouter](https://openrouter.ai) API key
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (free tunnel, no account required)

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/Agent-Field/af-reactive-atlas-mongodb.git
cd af-reactive-atlas-mongodb
cp .env.example .env
```

Edit `.env` with your values:

```env
OPENROUTER_API_KEY=sk-or-v1-...
MONGODB_URI=mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/reactive_intelligence?retryWrites=true&w=majority
```

### 2. Start AgentField

```bash
docker compose up -d
```

Two services start: the AgentField control plane at `http://localhost:8092` and the `reactive-intelligence` agent at `http://localhost:8004`.

### 3. Seed Atlas

```bash
python3 setup/seed.py all
```

Seeds both domains: accounts, customers, compliance rules, fraud rules, policies, and domain configuration documents.

### 4. Open a public tunnel

Atlas Triggers require a public HTTPS URL to reach your local AgentField instance.

```bash
cloudflared tunnel --url http://localhost:8092
```

Copy the `https://xxxx.trycloudflare.com` URL for the next step.

### 5. Create Atlas Triggers

Create two triggers in [Atlas App Services](https://cloud.mongodb.com) — one for each domain.

**Trigger 1 — Finance:** Database trigger, Insert operation, collection `transactions`, Full Document enabled.

**Trigger 2 — E-commerce:** Database trigger, Insert operation, collection `orders`, Full Document enabled.

Use the same function for both triggers, replacing `YOUR_TUNNEL_URL`:

```javascript
exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (!doc || doc._intelligence) return;

  const collection = changeEvent.ns.coll;
  const domainMap = { transactions: "finance", orders: "ecommerce" };
  const domain = domainMap[collection] || "finance";

  const response = await context.http.post({
    url: "https://YOUR_TUNNEL_URL/api/v1/execute/async/reactive-intelligence.process_document",
    headers: { "Content-Type": ["application/json"] },
    body: JSON.stringify({
      input: { document: doc, collection: collection, domain: domain }
    })
  });

  if (response.statusCode >= 400) {
    throw new Error(`AgentField returned ${response.statusCode}`);
  }
};
```

### 6. Run a scenario

```bash
python3 demo.py finance structuring
python3 demo.py ecommerce velocity-abuse
```

---

## Demo commands

```bash
python3 demo.py list                    # list all domains and scenarios
python3 demo.py finance all             # run all finance scenarios in sequence
python3 demo.py ecommerce all           # run all ecommerce scenarios
python3 demo.py finance status          # show enrichment counts
python3 demo.py finance reset           # clear demo data, preserve base data

# custom document injection
python3 demo.py finance custom \
  --amount 75000 --country KY --type wire_transfer \
  --narrative "Consulting fees - offshore vehicle"

python3 demo.py ecommerce custom \
  --amount 999 --country US \
  --narrative "Rush order electronics"
```

Every run uses randomized amounts and IDs. No two runs produce identical documents.

---

## What to watch

**In Atlas UI** (`cloud.mongodb.com` -> Browse Collections):

- `transactions` and `orders` — each document gains `_intelligence` within 10-15 seconds of insert
- `reaction_timeline` — every AI decision logged with timestamps, scores, and triggered policies
- `accounts` and `customers` — risk profiles update when cascade fires on high-risk documents

**In AgentField UI** (`http://localhost:8092`):

- Each insert creates a visible execution trace for `process_document`
- The trace shows every skill call: config load, entity lookup, rule retrieval, LLM reasoning, enrichment write, policy evaluation, cascade

---

## Under the hood

Built on [AgentField](https://github.com/Agent-Field/agentfield) — a framework for running AI agents as microservices with built-in observability, async execution, and structured skill composition.

| Skill | What it does |
|---|---|
| `load_domain_config` | Load domain config from MongoDB — all behavior derives from this |
| `load_entity_context` | Fetch entity profile (account, customer, device, patient) |
| `find_related_documents` | Load historical documents for context |
| `load_rules` | Retrieve relevant domain rules via text search |
| `enrich_document` | Write `_intelligence` back into the source document |
| `load_active_policies` | Load domain-scoped policies (plain English, not code) |
| `update_entity_risk` | Propagate risk changes to linked entities |
| `log_reaction` | Append to `reaction_timeline` for full audit trail |

Skills handle deterministic MongoDB operations. The LLM handles judgment. The split is intentional: skills are auditable and testable; the reasoner handles the parts that require contextual interpretation.

This is different from a chatbot — intelligence runs on database events and mutates operational data. This is different from a rule engine — policies are semantic, written in plain English, evaluated with judgment.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM API key via OpenRouter |
| `MONGODB_URI` | Yes | Atlas connection string |
| `AGENTFIELD_PUBLIC_URL` | Yes | Tunnel URL Atlas uses to reach local AgentField |
| `MONGODB_DATABASE` | No | Database name (default: `reactive_intelligence`) |
| `AI_MODEL` | No | LLM model ID (default: `openrouter/minimax/minimax-m2.5`) |
| `AGENTFIELD_URL` | No | Local control plane URL (default: `http://localhost:8092`) |

---

## Project structure

```
.
├── main.py                  # Agent entry point
├── models.py                # Pydantic models (DocumentIntelligence, PolicyEvaluation, CascadeResult)
├── reasoners/
│   ├── intelligence.py      # process_document reasoner + cascade logic
│   ├── skills.py            # Generic MongoDB skill implementations
│   └── router.py            # AgentField router setup
├── domains/
│   ├── finance/             # AML compliance: 50 accounts, 20 rules, 5 policies, 5 scenarios
│   └── ecommerce/           # Order fraud: 40 customers, 15 rules, 5 policies, 5 scenarios
├── setup/
│   └── seed.py              # Generic seeder (reads from domains/)
├── demo.py                  # Domain-aware demo runner
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## Related

- [AgentField](https://github.com/Agent-Field/agentfield) — the AI Backend framework powering this pattern
- [agentfield.ai](http://www.agentfield.ai) — documentation and additional examples

---

## License

MIT
