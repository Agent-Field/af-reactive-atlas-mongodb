# Reactive Atlas

**MongoDB Atlas as an AI Backend — documents that self-enrich via Atlas Triggers and AgentField.**

[![AgentField](https://img.shields.io/badge/Powered%20by-AgentField-6366f1?style=flat-square)](https://github.com/Agent-Field/agentfield)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-00ED64?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## How it works

A document is inserted into MongoDB Atlas. An Atlas Trigger fires immediately, passing the full document to AgentField. AgentField runs a reasoning agent that loads domain configuration from the database, fetches entity context, retrieves relevant rules, and calls an LLM to produce a structured judgment. The result is written back into the source document as `_intelligence`. Policy evaluation runs next. If the risk score crosses a threshold, a cascade fires to update linked entities. Every step is logged to `reaction_timeline`.

The database initiates intelligence. Your application code does nothing.

The behavior of the AI — what it analyzes, what rules it applies, what policies it enforces, when it cascades — is entirely driven by configuration documents stored in MongoDB. Change what the AI does by changing MongoDB documents, not code.

---

## Two domains shipped

This repository ships two complete domains to demonstrate that the pattern is universal.

**Finance (AML compliance)** — triggers on the `transactions` collection:

| Scenario | What it represents |
|---|---|
| `clean` | Normal business transfers; baseline for low-risk scoring |
| `structuring` | Five cash deposits just under $10K; each legal, the pattern is not |
| `round-trip` | A to B to C back to A with slight value decay; intent hidden across hops |
| `layering` | US to HK to KY to CH SWIFT chain; each hop looks normal in isolation |
| `big-one` | Single $500K to $1.2M Cayman wire; high-value plus jurisdiction triggers policy |

**E-commerce (order fraud)** — triggers on the `orders` collection:

| Scenario | What it represents |
|---|---|
| `normal` | Legitimate purchase; baseline for low-risk scoring |
| `velocity-abuse` | Rapid repeat orders from the same customer in a short window |
| `friendly-fraud` | High-value order with a history of chargebacks on the account |
| `synthetic-identity` | New account, no history, high-value order, mismatched signals |
| `high-value-mismatch` | Order value inconsistent with account tenure and purchase history |

Both domains run on the same agent, the same skills, and the same reasoning loop. The domain configuration in MongoDB tells the engine what to do for each collection.

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
