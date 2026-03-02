# Reactive Atlas

**MongoDB Atlas as an AI Backend — documents that self-enrich via Atlas Triggers and AgentField.**

[![AgentField](https://img.shields.io/badge/Powered%20by-AgentField-6366f1?style=flat-square)](https://github.com/Agent-Field/agentfield)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-00ED64?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## What this is

Reactive Atlas turns any MongoDB collection into an **intelligent data layer**. Documents inserted into Atlas are automatically analyzed, enriched, and acted upon by an AI agent — no application code, no polling, no rule engines.

The core idea: **your database already knows when data changes. Let it trigger intelligence.**

- A new transaction lands in `transactions` — the AI scores it for money laundering risk, flags suspicious patterns, and updates linked account profiles
- A new order lands in `orders` — the AI evaluates it for fraud signals, checks velocity patterns, and holds high-risk orders for review
- A new patient record lands in `intake` — the AI triages urgency, cross-references drug interactions, and routes to the right department

Same engine. Same code. Different config document in MongoDB.

---

## How it works

```mermaid
flowchart TD
    A["Document inserted into Atlas"] --> B["Atlas Trigger fires"]
    B --> C["AgentField resolves domain from collection"]
    C --> D["Loads config + entity context + rules"]
    D --> E["LLM produces structured judgment"]
    E --> F["_intelligence written back to document"]
    F --> G{"Risk above threshold?"}
    G -- Yes --> H["Cascade: update entities,\nre-enrich related docs"]
    G -- No --> I["Log to reaction_timeline"]
    H --> I
```

Step by step:

1. **Document insert** — your app (or a feed, API, ETL) writes a document to an Atlas collection
2. **Atlas Trigger** — MongoDB's built-in [Database Trigger](https://www.mongodb.com/docs/atlas/app-services/triggers/) fires on the insert and calls AgentField over HTTPS
3. **Domain resolution** — AgentField maps the collection name to a domain (`transactions` -> `finance`, `orders` -> `ecommerce`) and loads the domain's config document from MongoDB
4. **Context assembly** — the agent fetches the entity profile (account, customer, patient), recent history from the same collection, and relevant domain rules via text search
5. **LLM reasoning** — all context is passed to the LLM with the domain-specific analysis prompt. The LLM returns a structured `DocumentIntelligence` object: risk score, risk category, detected pattern, applicable rule IDs, and a summary
6. **In-place enrichment** — the result is written back into the source document as `_intelligence`. The original document is untouched; intelligence is additive
7. **Policy evaluation** — active policies (written in plain English) are evaluated against the enriched document. Policies trigger actions like `flag`, `hold`, `investigate`, or `escalate`
8. **Cascade** — if the risk score exceeds a configurable threshold, the agent updates the entity's risk profile and re-enriches related unenriched documents in the same collection
9. **Audit trail** — every decision is logged to `reaction_timeline` with timestamps, scores, and triggered policies

**The database initiates intelligence. Your application code does nothing.**

All AI behavior — the analysis prompt, which rules to load, when to cascade, what policies to enforce — lives in a MongoDB config document. Change the config, change the behavior. No code changes. No redeploy.

---

## Use cases

Reactive Atlas works on **any domain where documents arrive and need intelligent assessment**. The engine is generic; the domain config makes it specific.

| Domain | Collection | What the AI does |
|---|---|---|
| **Financial compliance** | `transactions` | AML pattern detection, sanctions screening, structuring and layering identification, counterparty risk propagation |
| **E-commerce fraud** | `orders` | Velocity abuse detection, synthetic identity signals, friendly fraud patterns, address mismatch flagging |
| **Healthcare triage** | `patient_intake` | Urgency scoring, drug interaction alerts, department routing, insurance pre-authorization checks |
| **Content moderation** | `posts` | Toxicity scoring, policy violation detection, escalation routing, context-aware nuance beyond keyword matching |
| **Cybersecurity** | `security_events` | Threat classification, anomaly scoring against baseline behavior, incident severity assessment, lateral movement detection |
| **Insurance claims** | `claims` | Fraud signal detection, damage assessment consistency, claimant history cross-referencing, fast-track vs. investigation routing |
| **IoT / Telemetry** | `sensor_readings` | Anomaly detection against device baselines, predictive maintenance triggers, fleet-wide pattern correlation |
| **Supply chain** | `shipments` | Delay risk scoring, vendor reliability assessment, customs compliance flagging, route anomaly detection |

To build any of these, you create a `domains/yourname/` directory with a config file, seed it, and point an Atlas Trigger at the collection. Zero Python changes.

### Shipped examples

This repo includes two fully worked domains you can run immediately:

**[Finance (AML compliance)](domains/finance/)** — triggers on `transactions`, seeds 50 accounts + 20 compliance rules + 5 policies:

| Scenario | What happens |
|---|---|
| `clean` | 3 normal business transfers — baseline, should score low |
| `structuring` | 5 cash deposits just under $10K — each legal, the pattern is not |
| `round-trip` | A->B->C->A circular transfer — intent hidden across 3 hops |
| `layering` | US->HK->KY->CH SWIFT chain — each hop looks normal in isolation |
| `big-one` | Single $500K-$1.2M Cayman wire — high-value + jurisdiction triggers policy |

**[E-commerce (order fraud)](domains/ecommerce/)** — triggers on `orders`, seeds 40 customers + 15 fraud rules + 5 policies:

| Scenario | What happens |
|---|---|
| `normal` | 3 legitimate orders — baseline, should score low |
| `friendly-fraud` | Expensive items from a customer with high return history |
| `velocity-abuse` | 5 rapid orders, different shipping addresses, expedited shipping |
| `synthetic-identity` | New accounts, mismatched billing/shipping, high-value electronics |
| `high-value-mismatch` | Large cross-border electronics order from a new account |

Both run on the same agent, same skills, same reasoning loop. The only difference is the config document in MongoDB.

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

Seeds both domains: accounts, customers, AML rules, fraud rules, compliance policies, and domain configuration documents.

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
# List all available scenarios
python3 demo.py list

# Finance domain
python3 demo.py finance clean
python3 demo.py finance structuring
python3 demo.py finance round-trip
python3 demo.py finance layering
python3 demo.py finance big-one
python3 demo.py finance all
python3 demo.py finance status
python3 demo.py finance reset

# E-commerce domain
python3 demo.py ecommerce normal
python3 demo.py ecommerce velocity-abuse
python3 demo.py ecommerce friendly-fraud
python3 demo.py ecommerce synthetic-identity
python3 demo.py ecommerce high-value-mismatch
python3 demo.py ecommerce all
python3 demo.py ecommerce status
python3 demo.py ecommerce reset

# Custom injection
python3 demo.py finance custom --amount 75000 --country KY --type wire_transfer --narrative "Consulting fees"
python3 demo.py ecommerce custom --amount 999 --country US --narrative "Rush order electronics"
```

Every run uses randomized amounts and IDs. No two runs produce identical documents.

---

## What to watch

**In Atlas UI** (`cloud.mongodb.com` → Browse Collections):

- `transactions` and `orders` — each document gains `_intelligence` within 10 to 15 seconds of insert
- `_intelligence` contains the risk score, reasoning, detected patterns, and policy outcomes
- `reaction_timeline` — policy decisions and cascade events logged in real time
- `accounts` and `customers` — risk profiles updated when cascade fires

**In AgentField UI** (`http://localhost:8092`):

- Each insert creates a visible async execution for `reactive-intelligence.process_document`
- The execution trace shows every skill call in sequence: domain config load, entity context, rule retrieval, enrichment write, policy evaluation, cascade, timeline log

---

## Build your own domain

Adding a third domain requires no Python code changes. The engine is fully config-driven.

### 1. Create the domain directory

```
domains/yourname/
  config.json      # Collection name, entity type, context loading, cascade rules
  entities.json    # Seed data for accounts, customers, or whatever your entity is
  rules.json       # Domain-specific rules the AI reasons over
  policies.json    # Natural-language policies evaluated after enrichment
  scenarios.json   # Named scenarios with document templates
```

`config.json` is the control surface. It tells the engine which collection to watch, how to load entity context, what prompt to use for reasoning, which fields to index for rule retrieval, and when to trigger a cascade. Change the config document in MongoDB and the behavior changes immediately — no redeploy.

### 2. Seed your domain

```bash
python3 setup/seed.py yourname
```

### 3. Create an Atlas Trigger

Add your collection to the `domainMap` in the trigger function and create a new trigger on your collection. The same function handles all domains.

### 4. Run your scenarios

```bash
python3 demo.py yourname yourscenario
```

---

## How it works (under the hood)

Built on [AgentField](https://github.com/Agent-Field/agentfield) — a framework for running AI agents as microservices with built-in observability, async execution, and structured skill composition.

The `process_document` reasoner orchestrates these skills in sequence:

| Skill | What it does |
|---|---|
| `load_domain_config` | Load domain configuration from MongoDB |
| `load_entity_context` | Fetch entity profile (account, customer, etc.) |
| `find_related_documents` | Load historical documents for context |
| `load_rules` | Retrieve relevant domain rules via text search |
| `enrich_document` | Write `_intelligence` back into the source document |
| `load_active_policies` | Load domain-scoped policies |
| `update_entity_risk` | Propagate risk changes to entities |
| `log_reaction` | Append events to `reaction_timeline` |

Skills handle deterministic MongoDB operations. The LLM handles judgment. The split is intentional: skills are auditable and testable; the reasoner handles the parts that require contextual interpretation.

This is different from a chatbot: intelligence runs on database events and mutates operational data directly. This is different from a static rule engine: policy evaluation is semantic — you write intent in plain English, not if-else conditions.

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
├── models.py                # Pydantic models
├── reasoners/
│   ├── intelligence.py      # process_document reasoner and cascade logic
│   ├── skills.py            # MongoDB skill implementations
│   └── router.py            # AgentField router setup
├── domains/
│   ├── finance/             # AML compliance domain config
│   │   ├── config.json
│   │   ├── entities.json
│   │   ├── rules.json
│   │   ├── policies.json
│   │   └── scenarios.json
│   └── ecommerce/           # Order fraud domain config
│       ├── config.json
│       ├── entities.json
│       ├── rules.json
│       ├── policies.json
│       └── scenarios.json
├── setup/
│   └── seed.py              # Seeds Atlas with domain data
├── demo.py                  # Demo runner with randomized scenarios
├── docker-compose.yml       # AgentField control plane and agent
├── Dockerfile               # Agent container
└── .env.example             # Environment variable template
```

---

## Related

- [AgentField](https://github.com/Agent-Field/agentfield) — the AI Backend framework powering this pattern
- [agentfield.ai](http://www.agentfield.ai) — documentation and additional examples

---

## License

MIT
