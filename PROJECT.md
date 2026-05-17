# PROJECT.md — AdaptInsure: AI-Powered Insurance Adapter Platform

> **Author:** Bhargavi | Weekly Weights
> **Stack:** Python 3.12 | FastAPI | Gemini API | Pydantic | Jinja2 | pytest

---

## What This Is

AdaptInsure is a meta-adapter platform for insurance claims data. It takes a new insurer's sample data — whether that's JSON from a modern REST API, XML from a SOAP endpoint, CSVs from a legacy mainframe, or ACORD-formatted messages — analyzes the schema, maps every field to a universal insurance claims model, generates a production-grade Python adapter with full test coverage, and continuously monitors for schema drift in production.

This is not a generic ETL tool. It is purpose-built for insurance claims data, informed by ACORD standards, Guidewire ClaimCenter data models, and Duck Creek Claims architecture. Every mapping understands insurance domain semantics — it knows that "excess" means "deductible," that "FNOL" means "First Notice of Loss," and that a Guidewire Exposure is a coverage-level line item where financials are tracked.

---

## The Problem

Insurance is an $8 trillion industry where the backbone — claims processing — still runs on fragmented, incompatible technology. Every carrier operates on a different stack:

- Carrier A runs Guidewire ClaimCenter with camelCase JSON REST APIs
- Carrier B runs Duck Creek Claims with SOAP/XML and 2,600+ proprietary APIs
- Carrier C exports nightly CSVs from a mainframe with field names like CLM_DT_OF_LSS and CLMNT_NM
- Carrier D sends ACORD XML but with custom extensions, missing required fields, and date formats that don't match the spec
- Carrier E uses an in-house system nobody documented, and the only artifact is a 200-row Excel data dictionary from 2019

Any InsurTech company building on top of carrier data hits the same wall: every new client is a multi-week custom integration project. An engineer has to manually read API docs, understand the schema, write field mappings, handle format conversions, build validation, write tests, and then maintain it all when the carrier inevitably changes something without telling anyone.

AdaptInsure automates this entire pipeline.

---

## How It Works

```
Feed sample data + API docs/schema
        |
   Discovery Engine (LLM-powered)
   Analyzes format, detects fields, infers types, builds client profile
        |
   Structured Client Profile (JSON)
        |
   Mapping Engine (LLM + domain knowledge)
   Matches client fields to universal schema with confidence scores
   Flags ambiguities for human review
        |
   Mapping Config (JSON)
   { "field_mappings": {...}, "transforms": {...}, "gaps": [...] }
        |
   Adapter Generator (deterministic — Jinja2 templates)
   Generates typed Python adapter class from config
   LLM decides the config, templates decide the code
        |
   Generated Adapter + Auto-Generated Tests
        |
   Human reviews and approves
        |
   Deployed to production
        |
   Drift Monitor (continuous)
   Compares incoming data against expected schema
   Alerts on field renames, type changes, new fields, missing fields
   Proposes config fix — human approves
```

The key architectural decision: LLMs handle intelligence (understanding schemas, semantic matching, detecting drift). Templates handle code generation (deterministic, testable, reviewable). JSON configs are the bridge between them. The LLM never writes production code directly.

---

## Research Findings

### ACORD Standards — The "Universal Language" That Isn't

ACORD (Association for Cooperative Operations Research and Development) is the global standard body for insurance data exchange. Founded in 1970, used by ~90% of US P&C carriers.

What ACORD defines:
- XML and AL3 formats covering P&C, Life, and Reinsurance lines
- P&C XML covers FNOL, claims, accounting transactions, policy data
- Standard forms: ACORD 25 (Certificate of Liability), ACORD 125 (Commercial App), ACORD 126 (Commercial GL), ACORD 131 (Umbrella/Excess), ACORD 140 (Property)
- Reference Architecture: Information Model, Data Model, Process Model, Capability Model
- Standardized data types: ISO 8601 dates, decimal precision, currency codes, unique IDs

The critical insight: ACORD standards are "merely suggestions" in practice. Industry analysis confirms "the quality of data downloaded varies greatly depending on the insurer." Every carrier implements ACORD differently — field names vary, required fields become optional, custom extensions are everywhere, and version adoption is inconsistent.

Existing ACORD tooling:
- eiConsole: IDE for building ACORD interfaces and validation (Java/XML)
- JAXB / XMLSerializer / lxml: code bindings from XSD files
- ACORD Validation Engine: checks compliance against official schemas
- UiPath ACORD accelerators: ML models for form field extraction (ACORD 25, 125, 126, 131, 140)

None of these handle the real-world problem: every carrier deviates from the standard differently, and the deviations are where all the integration work lives.

### Guidewire ClaimCenter — Dominant CMS

Guidewire ClaimCenter is the most widely used P&C claims management system. Implementation costs start at $500K+. Deployment timelines run 12-24 months.

Architecture:
- Relational, backed by Oracle/SQL Server/PostgreSQL
- Highly normalized with clear entity boundaries
- Entity-centric — business concepts map to entity definitions
- Metadata-driven, configured via entity XML files
- Cloud API is REST-based JSON for modern integrations
- Gosu scripting language for business rules

Core data model:
```
Claim (parent for everything)
  Fields: lossDate, reportedDate, claimState, status, claimNumber
  Lifecycle: open -> closed -> reopened

  Exposure[] (loss components — financials tracked here)
    Links to: coverage verification, reserves, payments, recoveries
    Types: vehicle damage, bodily injury, property damage
    Workflows and approvals are exposure-driven

  Incident[] (inheritance hierarchy)
    VehicleIncident (make, model, VIN, damage description)
    InjuryIncident (body part, severity, treatment)
    PropertyIncident (address, damage type, valuation)

  Contact + ContactRole (separated — same person can be driver AND claimant)
    Contact = person or organization (reusable across claims)
    ContactRole = role on THIS claim (insured, claimant, witness, attorney)

  Transaction[] (immutable once posted — full audit trail)
    Payment, Recovery, Reserve
    Check entity for multi-payment support, voids, reissues

  Activity[] (tasks, reminders, approvals — SLA driven)
  Note[], Document[] (decoupled from core data)
```

API patterns: camelCase field naming. Resources map to multiple entities (ClaimContact -> ClaimContact + Contact + ClaimContactRole). Typelists for enums. DB tables follow CC_ prefix: CC_CLAIM, CC_EXPOSURE, CC_TRANSACTION, CC_CONTACT.

### Duck Creek Claims — Second Major Player

Duck Creek is cloud-native, API-first, with 2,600+ REST APIs. Low-code configuration model.

Architecture:
- RESTful APIs and legacy SOAP interfaces
- ManuScript-driven configuration (proprietary scripting)
- Low-code for business rules
- Covers full claims lifecycle: FNOL, assignment, investigation, evaluation, negotiation, settlement
- Subscription pricing scaled to premium volume ($200K-$800K/year)
- Smaller integration ecosystem than Guidewire but growing fast

Same core concepts as Guidewire (claims, exposures, parties, payments) but different schema, different field names, different API patterns, different data types.

### LLM-Powered Schema Mapping — Academic Validation

The hybrid approach (LLM for intelligence + deterministic execution) is validated by recent academic work:

MetaConfigurator (University of Stuttgart, 2025-2026):
- Open-source tool combining LLMs with deterministic safeguards for JSON schema mapping
- Key insight: LLMs generate human-readable mapping rules, then rules are executed deterministically
- Separation of generation from execution ensures reliability and scalability
- Handles JSON, CSV, XML, YAML heterogeneous sources
- Finding: LLMs struggle with large inputs — must pre-process and chunk before sending to LLM
- Finding: LLM reasoning degrades as input length increases, even before max context window

PyDI (University of Mannheim, 2026):
- Fully automated end-to-end data integration pipeline using LLMs
- LLM performs schema matching, value normalization, entity matching, validation data generation
- Compared against human-designed pipelines — competitive results
- Open source: github.com/wbsg-uni-mannheim/PyDI

Industry best practices from production LLM schema mapping:
- Always validate after AI mapping
- Store successful mappings to build knowledge base over time
- Keep humans in the loop for critical integrations
- Test with small samples before full migration

---

## Universal Insurance Claims Schema

The canonical data model that all adapters map to. Informed by ACORD, Guidewire, and Duck Creek but simplified for practical use. Implemented as Pydantic models with strict validation.

### Core Entities

Claim — the central record
```
claim_id: str
claim_number: str
status: ClaimStatus (open | closed | reopened | denied | pending)
loss_date: datetime
reported_date: datetime
closed_date: datetime | None
loss_description: str
loss_cause: str
loss_location: Address
line_of_business: str (Auto, Property, GL, Workers Comp, etc.)
policy_number: str
policy_effective_date: datetime
policy_expiration_date: datetime
total_incurred: Decimal
total_paid: Decimal
total_reserved: Decimal
deductible: Decimal
catastrophe_code: str | None
litigation_flag: bool
subrogation_flag: bool
fraud_flag: bool
adjuster_id: str | None
adjuster_name: str | None
created_at: datetime
updated_at: datetime
source_system: str
raw_data: dict
```

Exposure — coverage-level line item within a claim
```
exposure_id: str
claim_id: str
exposure_type: ExposureType (vehicle_damage | bodily_injury | property_damage | med_pay | pip | um_uim | liability | other)
coverage_type: str
status: ExposureStatus (open | closed)
reserved_amount: Decimal
paid_amount: Decimal
deductible_amount: Decimal
claimant_id: str
```

Claimant — person or organization
```
claimant_id: str
claim_id: str
role: ContactRole (insured | claimant | witness | attorney | adjuster | vendor | other)
first_name: str
last_name: str
organization_name: str | None
email: str | None
phone: str | None
address: Address | None
date_of_birth: date | None
```

Transaction — financial movement
```
transaction_id: str
claim_id: str
exposure_id: str | None
transaction_type: TransactionType (payment | recovery | reserve_set | reserve_change)
amount: Decimal
currency: str (ISO 4217)
transaction_date: datetime
check_number: str | None
payee_name: str | None
status: TransactionStatus (pending | approved | posted | voided)
```

PolicySnapshot — policy data at time of loss
```
policy_number: str
carrier_name: str
product_type: str
effective_date: datetime
expiration_date: datetime
insured_name: str
coverages: list[Coverage]
premium: Decimal
```

Address
```
street_1: str
street_2: str | None
city: str
state: str
postal_code: str
country: str (ISO 3166-1 alpha-2)
```

---

## Architecture

```
adapt-insurance/
├── .cursorrules
├── PROJECT.md
├── TASKS.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── src/
│   ├── config.py
│   ├── schema/           # Universal claims schema (Pydantic models, enums, validators)
│   ├── discovery/         # Analyze incoming data formats
│   │   ├── engine.py
│   │   ├── parsers/       # json_parser, xml_parser, csv_parser, doc_parser
│   │   ├── analyzer.py    # LLM-powered field analysis
│   │   └── profile.py     # ClientProfile model
│   ├── mapping/           # Map client fields to universal schema
│   │   ├── engine.py
│   │   ├── semantic_matcher.py
│   │   ├── transform_detector.py
│   │   ├── gap_analyzer.py
│   │   ├── confidence.py
│   │   └── config.py      # MappingConfig model
│   ├── generator/         # Generate adapter code from config
│   │   ├── engine.py
│   │   ├── templates/     # Jinja2 templates (adapter_class, transforms, validator, tests)
│   │   └── registry.py
│   ├── testing/           # Auto-generated test harness
│   │   ├── contract_tests.py
│   │   ├── roundtrip.py
│   │   ├── edge_cases.py
│   │   └── reporter.py
│   ├── monitor/           # Drift detection + alerting
│   │   ├── detector.py
│   │   ├── differ.py
│   │   ├── alerter.py
│   │   └── proposer.py
│   └── api/               # FastAPI endpoints
│       ├── app.py
│       └── routes/        # discovery, mapping, generate, test, monitor
├── samples/               # Synthetic insurer data (3 formats)
│   ├── guidewire_carrier/
│   ├── acord_carrier/
│   └── legacy_carrier/
├── generated/             # Output — generated adapters
├── tests/                 # Tests for the platform itself
└── docs/                  # Phase specs
```

---

## Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Language | Python 3.12 | Insurance tooling ecosystem, Pydantic, fast prototyping |
| API | FastAPI | Async, typed, auto-docs |
| Data models | Pydantic v2 | Strict validation, JSON schema generation, serialization |
| LLM | Gemini API (google-genai; gemini-2.5-flash / gemini-2.5-pro) | Structured output, domain knowledge |
| Code generation | Jinja2 | Deterministic template rendering |
| XML parsing | lxml | Industry standard for ACORD XML |
| CSV parsing | pandas | Handles messy CSVs, encoding issues, delimiter detection |
| OpenAPI parsing | pyyaml + jsonschema | Parse Swagger/OpenAPI specs |
| Testing | pytest | Auto-generated tests + platform tests |
| Monitoring | difflib + LLM | Schema diff detection |

---

## Phases

### Phase 1: Universal Schema + Base Adapter Interface
Build the canonical insurance data model and the abstract adapter contract.
- All Pydantic models (Claim, Exposure, Claimant, Transaction, PolicySnapshot, Address)
- All enums (ClaimStatus, ExposureType, ContactRole, TransactionType, TransactionStatus)
- Custom validators (date ranges, amount non-negative, required field checks)
- Base adapter abstract class: parse_raw(), map_record(), validate_record(), transform_batch()
- Error taxonomy — every failure mode typed and categorized
- Unit tests for all models and validators

### Phase 2: Discovery Engine
Analyze any incoming data format and produce a structured client profile.
- Format detection (JSON, XML, CSV, fixed-width)
- Parsers: JSON/OpenAPI, XML/WSDL/ACORD, CSV/fixed-width, markdown data dictionaries
- LLM analyzer — produces ClientProfile with field descriptions, inferred semantics, domain annotations
- ClientProfile Pydantic model
- Tests with all three synthetic insurer formats

### Phase 3: Mapping Engine
Match client fields to the universal schema with confidence scores.
- Semantic matcher — LLM-powered fuzzy matching with insurance domain context
- Direct matches, semantic matches, computed fields
- Format transform detection (dates, currency, enums, strings)
- Gap analysis — missing, extra, ambiguous fields
- Confidence scoring per mapping
- MappingConfig output as JSON
- Knowledge base for improving future mappings
- Tests with all three synthetic insurers

### Phase 4: Adapter Code Generator
Generate production-grade adapter code from mapping configs.
- Jinja2 templates for adapter class, transforms, validators, tests
- Generated code is clean, typed, documented Python
- Implements base adapter interface from Phase 1
- Adapter registry for routing incoming data
- End-to-end: synthetic data -> discovery -> mapping -> generation -> adapter works

### Phase 5: Test Harness + Synthetic Insurers
Build three realistic fake insurers and automated testing.
- Insurer A: Guidewire-style (camelCase JSON, REST patterns, Guidewire field names)
- Insurer B: ACORD XML (namespaces, custom extensions, missing fields, older dates)
- Insurer C: Legacy mainframe (pipe-delimited, uppercase with underscores, packed dates)
- Contract tests, round-trip validation, LLM-generated edge cases
- Test report with pass/fail and field-level accuracy

### Phase 6: Drift Monitor + Alert System
Continuous monitoring for schema changes.
- Schema monitor comparing incoming data vs expected schema
- Field-level drift detection (rename, remove, type change, new field, format change)
- Human-readable alerts with proposed fix
- Approval workflow for config updates
- Drift history log
- Simulated drift scenarios for demo

---

## What This Is NOT

- Not a claims processing system — it doesn't adjudicate or pay claims
- Not a policy admin system — it doesn't manage policies
- Not an ACORD validator — it doesn't check compliance with ACORD specs
- Not a generic data pipeline — it is specifically for insurance claims data
- Not deployed — production-grade prototype, not a running service
- Not using real insurer data — all sample data is synthetic
