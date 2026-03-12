# Reactive Atlas — General-Purpose Architecture

## Core Concept

The agent reads a **domain configuration document** from MongoDB at processing time.
The domain config tells the engine: what collection to watch, how to load context,
what rules to evaluate, how to reason, when to cascade. All Python code is generic.

## New File Structure

```
reactive-atlas/
├── main.py                    # Agent entry point (reads DOMAIN env var)
├── models.py                  # Generic Pydantic models (domain-agnostic)
├── reasoners/
│   ├── __init__.py
│   ├── router.py              # AgentField router
│   ├── skills.py              # Generic MongoDB skills
│   └── intelligence.py        # Parameterized reasoner (reads config)
├── domains/
│   ├── finance/
│   │   ├── config.json        # Domain config document (seeded to MongoDB)
│   │   ├── entities.json      # 50 accounts
│   │   ├── rules.json         # 20 compliance rules
│   │   ├── policies.json      # 5 policies
│   │   └── scenarios.json     # 5 demo scenarios + custom spec
│   └── ecommerce/
│       ├── config.json        # Domain config document
│       ├── entities.json      # 40 customers + 30 products
│       ├── rules.json         # 15 fraud rules
│       ├── policies.json      # 5 policies
│       └── scenarios.json     # 5 demo scenarios + custom spec
├── setup/
│   └── seed.py                # Generic seeder: reads from domains/{name}/
├── demo.py                    # Generic demo: `python3 demo.py finance structuring`
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

## Domain Config Schema (MongoDB document in `domain_config` collection)

```json
{
  "domain": "finance",
  "display_name": "Financial Transaction Intelligence",
  "description": "AML compliance and financial crime detection",

  "document_collection": "transactions",
  "document_id_field": "transaction_id",

  "entity_collection": "accounts",
  "entity_id_field": "account_id",

  "rules_collection": "compliance_rules",

  "context_loading": {
    "entity_lookup_field": "account_id",
    "counterparty_field": "counterparty_id",
    "history_collection": "transactions",
    "history_match_fields": ["account_id", "counterparty_id"],
    "history_limit": 50
  },

  "enrichment_schema": {
    "risk_score": "float 0.0-1.0 indicating overall risk",
    "risk_category": "one of: low, medium, high, critical",
    "pattern_match": "detected pattern name or 'none'",
    "flags": "list of applicable rule IDs from the rules collection",
    "summary": "2-3 sentence executive summary"
  },

  "cascade_config": {
    "risk_threshold": 0.7,
    "update_entities": true,
    "reenrich_related": true,
    "counterparty_threshold": 0.8,
    "max_reenrich": 10
  },

  "analysis_prompt": "You are a financial crime analyst reviewing a banking transaction...",
  "policy_prompt": "Evaluate this document against each policy using judgment, not literal string matching."
}
```

## Generic Pydantic Models (models.py)

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class DocumentIntelligence(BaseModel):
    risk_score: float = Field(description="Risk score 0.0-1.0")
    risk_category: Literal["low", "medium", "high", "critical"]
    pattern_match: str = Field(description="Detected pattern name, or 'none'")
    flags: List[str] = Field(description="Applicable rule IDs from the domain rules")
    summary: str = Field(description="2-3 sentence executive summary")

class PolicyEvaluation(BaseModel):
    policy_id: str
    triggered: bool
    action: str = Field(description="Action: enrich, escalate, investigate, flag, hold, none")
    reasoning: str

class PolicyEvaluationList(BaseModel):
    evaluations: List[PolicyEvaluation]

class CascadeResult(BaseModel):
    documents_affected: int
    entity_updates: List[str] = Field(description="Entity IDs whose risk profiles were updated")
    documents_reenriched: int
    summary: str
```

## Generic Skill Signatures (skills.py)

All skills are domain-agnostic. They take collection names and field names as parameters.

```python
@router.skill()
def load_domain_config(domain: str) -> dict
    # Reads from db["domain_config"].find_one({"domain": domain})

@router.skill()
def load_entity_context(entity_id: str, entity_collection: str, entity_id_field: str) -> dict
    # Reads from db[entity_collection].find_one({entity_id_field: entity_id})

@router.skill()
def find_related_documents(collection: str, match_field: str, match_value: str, limit: int = 50) -> dict
    # db[collection].find({match_field: match_value}).sort("timestamp", DESCENDING).limit(limit)
    # Also check "$or" with counterparty_field if provided

@router.skill()
def load_rules(query: str, rules_collection: str, k: int = 6) -> dict
    # Text search on db[rules_collection]

@router.skill()
def enrich_document(collection: str, id_field: str, document_id: str, intelligence: dict) -> dict
    # Writes _intelligence to db[collection] matching {id_field: document_id}
    # Handles versioning

@router.skill()
def load_active_policies(domain: str) -> dict
    # db["policies"].find({"active": True, "domain": domain})

@router.skill()
def update_entity_risk(entity_collection: str, entity_id_field: str, entity_id: str, risk_profile: str, reason: str) -> dict
    # Updates risk_profile and _risk_update on entity

@router.skill()
def log_reaction(event: dict) -> dict
    # Same as before — inserts into reaction_timeline

@router.skill()
def get_timeline(limit: int = 20) -> dict
    # Same as before
```

## Reasoner Flow (intelligence.py)

### process_document(document, collection, domain="finance")
1. Load domain config
2. Extract doc_id using config.document_id_field
3. Skip if already enriched
4. Call analyze_document(document, domain_config)
5. Call enrich_document(collection, id_field, doc_id, analysis)
6. Load policies, call evaluate_policies
7. If risk >= cascade threshold, call cascade
8. Log reaction
9. Return result

### analyze_document(document, domain_config)
1. Load entity context using config.context_loading.entity_lookup_field
2. Load related documents from config.context_loading.history_collection
3. Load rules from config.rules_collection using text search
4. Use config.analysis_prompt as the prompt template
5. Include enrichment_schema description so LLM knows the expected output format
6. Return DocumentIntelligence

### evaluate_policies(document, intelligence, policies)
- Same as before, already generic

### cascade(document, intelligence, domain_config)
1. Read cascade_config from domain_config
2. If risk >= threshold: update entity risk, find related docs, re-enrich unenriched
3. If counterparty_field exists and risk >= counterparty_threshold: update counterparty
4. Return CascadeResult

## demo.py Interface

```bash
python3 demo.py finance clean
python3 demo.py finance structuring
python3 demo.py finance all
python3 demo.py ecommerce normal
python3 demo.py ecommerce friendly-fraud
python3 demo.py ecommerce all
python3 demo.py finance custom --amount 50000 --country KY --type wire_transfer --narrative "..."
python3 demo.py ecommerce custom --amount 299 --country US --category electronics --narrative "..."
python3 demo.py list                    # list available domains and scenarios
python3 demo.py finance reset
python3 demo.py finance status
```

demo.py reads scenarios from domains/{name}/scenarios.json.

## scenarios.json Format

```json
{
  "order": ["normal", "friendly-fraud", "velocity-abuse", "synthetic-identity", "high-value-mismatch"],
  "scenarios": {
    "normal": {
      "title": "Normal Orders",
      "description": "Three legitimate orders from established customers.",
      "watch": ["Risk scores should stay low.", "No fraud patterns detected."],
      "documents": [
        {
          "order_id": "__AUTO__",
          "customer_id": "cust_0005",
          "amount": {"random": [50, 500]},
          ...
        }
      ]
    }
  },
  "custom_defaults": {
    "customer_id": "cust_0012",
    "currency": "USD",
    ...
  }
}
```

For `__AUTO__` values, demo.py generates a unique ID.
For `{"random": [low, high]}` values, demo.py generates a random value in range.
This keeps scenarios declarative in JSON rather than hardcoded in Python.

## seed.py Interface

```bash
python3 setup/seed.py finance       # seeds finance domain
python3 setup/seed.py ecommerce     # seeds ecommerce domain
python3 setup/seed.py all           # seeds all domains
```

seed.py reads from domains/{name}/:
1. config.json → inserts/upserts into domain_config collection
2. entities.json → inserts into the configured entity_collection
3. rules.json → inserts into the configured rules_collection
4. policies.json → inserts into policies collection (with domain field added)

Also creates appropriate indexes.

## Atlas Trigger Function (updated)

```javascript
exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (!doc || doc._intelligence) return;

  // The domain is determined by which collection triggered
  const domain = changeEvent.ns.coll === "orders" ? "ecommerce" : "finance";
  const collection = changeEvent.ns.coll;

  const response = await context.http.post({
    url: "https://YOUR_TUNNEL_URL/api/v1/execute/async/reactive-intelligence.process_document",
    headers: { "Content-Type": ["application/json"] },
    body: JSON.stringify({
      input: { document: doc, collection: collection, domain: domain }
    })
  });
};
```

## Key Constraints

1. All policies in MongoDB must have a "domain" field so load_active_policies can filter
2. The analysis_prompt in domain config should be detailed (5-10 sentences) telling the LLM
   exactly how to reason about documents in this domain
3. The enrichment_schema in domain config is passed to the LLM so it knows what fields to fill
4. The `_: bool = True` workaround is still needed for skills with no required params
   (load_active_policies has domain param now so this may not be needed, but keep for get_timeline)
5. models.py field `compliance_flags` is renamed to `flags` (generic)
