# AdaptInsure

**AI-powered adapter platform for insurance claims data. Feed it any carrier's data — it generates a production-grade adapter automatically.**

Every insurance carrier runs a different stack. One sends Guidewire JSON, another exports ACORD XML, another dumps pipe-delimited CSVs from a mainframe built in 1998. Each new carrier integration takes weeks of custom engineering work.

AdaptInsure turns that into minutes. Feed it sample data from any carrier, and it:

1. **Discovers** the schema — detects format, infers field types, annotates with insurance domain knowledge
2. **Maps** every field to a universal claims model — direct matching, LLM-powered semantic matching for fields like `excess_amt` → `deductible`, confidence scores on every mapping
3. **Generates** a production-grade Python adapter — deterministic Jinja2 templates, not LLM-generated code
4. **Tests** the adapter automatically — contract tests, round-trip validation, adversarial edge cases
5. **Monitors** for schema drift — detects when carriers rename fields, change formats, add or remove columns, and proposes fixes with human-in-the-loop approval

---

## How It Works

```
Raw carrier data (JSON / XML / CSV)
        │
        ▼
┌─────────────────────┐
│   Discovery Engine   │  Detect format, parse fields, infer types,
│                     │  LLM annotates insurance semantics
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Mapping Engine     │  Direct match → Knowledge base → Semantic match
│                     │  Confidence scores, gap analysis, transform detection
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Code Generator     │  Jinja2 templates → deterministic Python adapter
│                     │  LLM decides config, templates write code
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Test Harness       │  Contract tests, round-trip validation,
│                     │  LLM-generated edge cases, test reports
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Drift Monitor      │  Schema comparison, human-readable alerts,
│                     │  proposed fixes, approval workflow (on demand)
└─────────────────────┘
```

---

## Demo: Three Synthetic Carriers

The repo includes three realistic synthetic insurer datasets under `samples/`:

| Carrier | Sample path | Format | Quirks |
|---------|-------------|--------|--------|
| **Beacon Mutual** | `samples/guidewire_carrier/` | Guidewire-style JSON | camelCase fields, nested exposures/contacts/transactions, ISO dates, OpenAPI spec |
| **Heritage National** | `samples/acord_carrier/` | ACORD XML | PascalCase elements, namespaces, mixed currency formats, custom extensions |
| **Consolidated Mutual** | `samples/legacy_carrier/` | Legacy mainframe CSV | Pipe-delimited, uppercase abbreviated names (`CLM_NBR`, `DT_OF_LSS`), packed dates, amounts in cents, Y/N booleans, latin-1 encoding, multi-file join on `CLM_NBR` |

All three run through the full pipeline with passing integration tests.

---

## Universal Claims Schema

Every adapter maps to a single canonical data model — informed by ACORD standards, Guidewire ClaimCenter, and Duck Creek Claims but simplified for practical use.

**Core entities:** Claim, Exposure, Claimant, Transaction, PolicySnapshot, Address

All models are Pydantic v2 with strict validation. Monetary fields use `Decimal` (never float). All datetimes are timezone-aware. Enums use `StrEnum` for JSON serialization.

---

## Architecture

```
AdaptInsure/
├── src/
│   ├── schema/           # Universal claims schema (Pydantic models, enums, validators)
│   ├── discovery/        # Format detection, parsers (JSON/XML/CSV/doc), LLM analyzer
│   ├── mapping/          # Direct matcher, semantic matcher, transform detector, gap analyzer
│   ├── generator/        # Jinja2 templates, code generation engine, adapter registry
│   ├── testing/          # Contract tests, round-trip validation, edge cases, reporter
│   ├── monitor/          # Schema differ, alerter, fix proposer, approval workflow
│   └── llm/              # Gemini API client wrapper
├── samples/              # Three synthetic insurer datasets
├── generated/            # Output — generated adapters (gitignored)
├── data/                 # Runtime schemas, pending fixes (gitignored JSON)
└── tests/                # Full test suite
```

---

## Key Design Decisions

**LLM for intelligence, templates for code.** The LLM analyzes schemas and matches fields. Jinja2 templates generate the actual adapter code. Same config always produces the same code — deterministic, testable, reviewable.

**Confidence scores on every mapping.** Every field mapping has a confidence score (0.0–1.0) and a reasoning string. High confidence = auto-mapped. Low confidence = flagged for human review.

**Three-tier matching.** Direct matcher (rule-based, exact/camelCase/abbreviation) → Knowledge base (reuses proven mappings) → Semantic matcher (LLM-powered; e.g. `excess` = `deductible`, `FNOL` = `reported_date`).

**Human-in-the-loop everywhere.** Mapping configs are reviewed before adapter generation. Drift fixes go through an approval queue (`pending` → `approved` → `applied`); simple fixes can be marked auto-approved but are never silently applied.

**Insurance domain native.** Not a generic ETL tool. Understands ACORD, Guidewire naming, legacy mainframe patterns, and insurance terminology (BI, PD, PIP, subrogation, SIR, TPA, SIU).

---

## Tech Stack

| Component | Tool |
|-----------|------|
| Language | Python 3.12 |
| Data models | Pydantic v2 (strict mode) |
| LLM | Google Gemini API (`google-genai`) |
| Code generation | Jinja2 |
| XML parsing | lxml |
| CSV handling | csv, pandas (discovery) |
| API spec parsing | pyyaml, jsonschema |
| Testing | pytest, pytest-asyncio |

---

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Add your GEMINI_API_KEY to .env

# Run tests
pytest tests/ -v

# Full pipeline integration tests (three carriers)
pytest tests/test_full_pipeline.py -v -m integration

# Drift monitor scenario tests
pytest tests/test_drift_scenarios.py -v
```

**Drift monitor (programmatic):**

```python
from src.monitor import DriftDetector

detector = DriftDetector()
detector.bootstrap_baseline(client_name, mapping_config, profile)
report = await detector.check(client_name, incoming_data, mapping_config=config, profile=profile)
```

---

## Test Coverage

- **Schema models:** Enum values, Pydantic validation, cross-field validators, JSON round-trips
- **Discovery:** Format detection, JSON/XML/CSV/doc parsers, LLM annotation (mocked), engine orchestration
- **Mapping:** Direct matcher rules, semantic matching (mocked), transform detection, gap analysis, confidence scoring, knowledge base persistence
- **Generator:** Template rendering, syntax validation, adapter registry, dynamic import
- **Test harness:** Contract checks, round-trip field survival, edge case generation (mocked)
- **Drift monitor:** Eight drift types, alert generation, fix proposal (mocked Gemini), approval workflow, eight simulated carrier scenarios
- **End-to-end:** Sample data → discover → map → generate → adapter transforms claims
- **Integration:** All three synthetic insurers through the complete pipeline with minimum pass rates

---

## Research

This project is informed by:

- **ACORD P&C standards** — XML/AL3 formats, form structures, inconsistent carrier adoption in practice
- **Guidewire ClaimCenter data model** — Claim → Exposure hierarchy, Cloud API patterns
- **Duck Creek Claims architecture** — large REST surface, configuration-driven workflows
- **MetaConfigurator (Uni Stuttgart)** — LLM + deterministic safeguards for schema mapping
- **PyDI (Uni Mannheim)** — LLM data integration pipelines competitive with human-designed ETL

---

## Author

Bhargavi · Weekly Weights
