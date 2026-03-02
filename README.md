# Reactive Atlas

**MongoDB Atlas as an AI Backend — documents that think for themselves.**

Every transaction inserted into Atlas is automatically analyzed by an AI agent. No polling. No cron jobs. No rule engines. [Atlas Triggers](https://www.mongodb.com/docs/atlas/app-services/triggers/) fire on insert, call [AgentField](https://github.com/Agent-Field/agentfield), and the document is enriched in place — risk scores, pattern detection, compliance flags, all driven by LLM reasoning over live context.

[![AgentField](https://img.shields.io/badge/Powered%20by-AgentField-6366f1?style=flat-square)](https://github.com/Agent-Field/agentfield)
[![MongoDB Atlas](https://img.shields.io/badge/MongoDB-Atlas-00ED64?style=flat-square&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## How it works

```
INSERT transaction
       ↓
Atlas Trigger fires
       ↓
AgentField process_document
       ↓
  load account context
  load compliance rules
  LLM reasoning over full context
       ↓
  _intelligence written back to document
  policies evaluated in natural language
  cascade: re-score linked accounts
  reaction_timeline updated
```

The database initiates intelligence. Your application code does nothing.

---

## What the AI detects

| Scenario | What it looks like | Why static rules fail |
|---|---|---|
| `clean` | Normal business transfers | Baseline — should score low |
| `structuring` | 5 cash deposits just under $10K | Each deposit is legal; the pattern is not |
| `round-trip` | A→B→C→A with slight value decay | Intent is hidden across three hops |
| `layering` | US→HK→KY→CH SWIFT chain | Each hop looks normal in isolation |
| `big-one` | Single $500K–$1.2M Cayman wire | High-value + jurisdiction = policy trigger |

The AI reasoner combines transaction details, account profile, related activity, and policy intent in a single decision — and writes the result directly into the document.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Python 3.10+
- [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) account (free M0 tier is enough)
- [OpenRouter](https://openrouter.ai) API key
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (free tunnel, no account needed)

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

Two services start:
- **Control plane** at `http://localhost:8092` — AgentField orchestrator and UI
- **reactive-intelligence agent** at `http://localhost:8004` — your AI backend

### 3. Seed Atlas with base data

```bash
python3 setup/seed.py
```

Creates 50 accounts, 5 compliance policies, and 20 AML rules in Atlas.

### 4. Open a public tunnel

Atlas Triggers need a public URL to reach your local AgentField instance.

```bash
cloudflared tunnel --url http://localhost:8092
```

Copy the `https://xxxx.trycloudflare.com` URL — you'll use it in the next step.

### 5. Create the Atlas Trigger

In [Atlas App Services](https://cloud.mongodb.com):

1. Go to **Triggers** → **Add Trigger**
2. **Trigger Type**: Database
3. **Operation Type**: Insert
4. **Collection**: `transactions`
5. Enable **Full Document**
6. Paste this function, replacing `YOUR_TUNNEL_URL`:

```javascript
exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (!doc || doc._intelligence) return;

  const response = await context.http.post({
    url: "https://YOUR_TUNNEL_URL/api/v1/execute/async/reactive-intelligence.process_document",
    headers: { "Content-Type": ["application/json"] },
    body: JSON.stringify({
      input: { collection: "transactions", document: doc }
    })
  });

  if (response.statusCode >= 400) {
    throw new Error(`AgentField returned ${response.statusCode}`);
  }
};
```

### 6. Run a scenario

```bash
python3 demo.py reset
python3 demo.py structuring
```

Every run uses randomized amounts and IDs — no two runs look the same.

---

## Demo commands

```bash
python3 demo.py clean          # 3 normal business transactions
python3 demo.py structuring    # 5 cash deposits just under $10K
python3 demo.py round-trip     # 3-hop circular transfer A→B→C→A
python3 demo.py layering       # 4-hop cross-border SWIFT chain
python3 demo.py big-one        # single high-value Cayman wire
python3 demo.py all            # run all scenarios in sequence
python3 demo.py status         # show enrichment counts
python3 demo.py reset          # clear transactions, preserve accounts/policies

# inject a custom transaction
python3 demo.py custom \
  --amount 75000 \
  --country KY \
  --type wire_transfer \
  --narrative "Consulting fees - offshore vehicle"
```

---

## What to watch

**In Atlas UI** (`cloud.mongodb.com` → Browse Collections):

- `transactions` — each document gains `_intelligence` within ~10–15 seconds of insert
- `reaction_timeline` — policy decisions and cascade events logged in real time
- `accounts` — risk profiles updated when cascade fires on high-risk transactions

**In AgentField UI** (`http://localhost:8092`):

- Each insert creates a visible async execution for `reactive-intelligence.process_document`
- Execution trace shows every skill call: account load, compliance lookup, enrichment write, policy eval, cascade

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM API key via OpenRouter |
| `MONGODB_URI` | Yes | Atlas connection string |
| `AGENTFIELD_PUBLIC_URL` | Yes (for Trigger) | Tunnel URL Atlas uses to reach local AgentField |
| `MONGODB_DATABASE` | No | Database name (default: `reactive_intelligence`) |
| `AI_MODEL` | No | LLM model ID (default: `openrouter/minimax/minimax-m2.5`) |
| `AGENTFIELD_URL` | No | Local control plane URL (default: `http://localhost:8092`) |

---

## How it works (under the hood)

Built on [AgentField](https://github.com/Agent-Field/agentfield) — a framework for running AI agents as microservices with built-in observability, async execution, and structured skill composition.

**Skills** handle deterministic MongoDB operations:

| Skill | What it does |
|---|---|
| `load_account_context` | Fetch account profile and recent transaction history |
| `load_compliance_guidance` | Retrieve relevant AML rules from the database |
| `enrich_document` | Write `_intelligence` back into the transaction document |
| `evaluate_policies` | Check natural-language policies against enriched data |
| `cascade_risk` | Propagate risk scores to linked accounts and transactions |
| `log_reaction` | Append a timestamped entry to `reaction_timeline` |

**The `process_document` reasoner** orchestrates those skills into a single document-level judgment. It receives the raw transaction from the Atlas Trigger, calls skills in sequence, and decides whether to cascade based on the enriched result.

This is different from a chatbot: intelligence runs on database events and mutates operational data directly.
This is different from a static workflow: policy evaluation is semantic — you write intent in plain English, not if-else rules.

---

## Project structure

```
.
├── main.py              # Agent entry point
├── models.py            # Pydantic models
├── reasoners/
│   ├── intelligence.py  # process_document reasoner + cascade logic
│   ├── skills.py        # MongoDB skill implementations
│   └── router.py        # AgentField router setup
├── setup/
│   └── seed.py          # Seeds Atlas with accounts, policies, rules
├── demo.py              # Demo runner with randomized scenarios
├── docker-compose.yml   # AgentField control plane + agent
├── Dockerfile           # Agent container
└── .env.example         # Environment variable template
```

---

## Related

- [AgentField](https://github.com/Agent-Field/agentfield) — the AI Backend framework powering this demo
- [agentfield.ai](http://www.agentfield.ai) — documentation and more examples

---

## License

MIT
