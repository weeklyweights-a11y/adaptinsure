# TASKS.md — AdaptInsure Build Phases

## Workflow

One phase at a time. For each phase:

1. Read the phase spec (docs/PHASE_X_SPEC.md)
2. Give it to Cursor: "Read .cursorrules, PROJECT.md, and docs/PHASE_X_SPEC.md. Create a plan. List every file you will create, what each contains, the order you will work, and dependencies. Wait for approval."
3. Review the plan — push back if it deviates from spec
4. Approve — Cursor builds
5. Run acceptance criteria at end of phase
6. All criteria pass — commit, tag: git tag -a phase-X-complete -m "Phase X done"
7. Move to next phase

If Cursor deviates from the spec, say: "Go back to the spec."
Do not move to the next phase until all acceptance criteria pass.

---

## Phase Overview

| Phase | What | Depends On | Key Deliverable |
|-------|------|-----------|----------------|
| 1 | Universal Schema + Base Adapter | Nothing | Pydantic models, enums, validators, base adapter ABC, error taxonomy |
| 2 | Discovery Engine | Phase 1 | Format detection, parsers (JSON/XML/CSV/doc), LLM analyzer, ClientProfile |
| 3 | Mapping Engine | Phase 1, 2 | Semantic matcher, transform detector, gap analysis, MappingConfig output |
| 4 | Adapter Code Generator | Phase 1, 3 | Jinja2 templates, generated adapter code, adapter registry |
| 5 | Test Harness + Synthetic Insurers | Phase 1-4 | 3 synthetic insurers, contract tests, edge cases, end-to-end validation |
| 6 | Drift Monitor + Alerts | Phase 1-4 | Schema drift detection, alerts, fix proposer, approval workflow |

---

## Phase 1: Universal Schema + Base Adapter Interface
**Spec:** docs/PHASE_1_SPEC.md
**Status:** [x] Complete

What gets built:
- All Pydantic models: Claim, Exposure, Claimant, Transaction, PolicySnapshot, Address, Coverage
- All enums: ClaimStatus, ExposureType, ExposureStatus, ContactRole, TransactionType, TransactionStatus, LineOfBusiness, LossCause
- Custom validators: date ranges, non-negative amounts, required field enforcement
- Base adapter abstract class with interface methods
- Error taxonomy: AdaptInsureError hierarchy
- config.py with settings
- Unit tests for all models and validators

Done means: all models instantiate with valid data, reject invalid data, validators catch edge cases, all tests pass.

---

## Phase 2: Discovery Engine
**Spec:** docs/PHASE_2_SPEC.md
**Status:** [x] Complete

What gets built:
- Format auto-detection (JSON vs XML vs CSV vs fixed-width)
- JSON parser: extract fields, types, nesting, sample values
- XML parser: elements, attributes, namespaces, ACORD version detection
- CSV parser: delimiter detection, header detection, type inference
- Doc parser: extract field definitions from text/markdown data dictionaries
- LLM analyzer: takes parsed structure, produces ClientProfile
- ClientProfile Pydantic model
- Tests with sample data from all three synthetic formats

Done means: feed any of the three sample formats, get back a valid ClientProfile with all fields identified and annotated.

---

## Phase 3: Mapping Engine
**Spec:** docs/PHASE_3_SPEC.md
**Status:** [x] Complete

What gets built:
- Semantic matcher with LLM and insurance domain context
- Direct matches, semantic matches, computed field detection
- Transform detector: date formats, currency, enum mapping, string normalization
- Gap analyzer: missing required, extra unmapped, ambiguous fields
- Confidence scoring per mapping (high/medium/low)
- MappingConfig Pydantic model as JSON output
- Successful mapping storage for knowledge base
- Tests: each synthetic insurer produces valid MappingConfig

Done means: ClientProfile from Phase 2 goes in, MappingConfig comes out with all fields mapped, transforms identified, gaps flagged, confidence scores assigned.

---

## Phase 4: Adapter Code Generator
**Spec:** docs/PHASE_4_SPEC.md
**Status:** [ ] Not started

What gets built:
- Jinja2 templates: adapter class, field transforms, validator, test file
- Generator engine: MappingConfig in, generated Python files out
- Generated code implements base adapter interface from Phase 1
- Adapter registry tracking all generated adapters
- Generated test file per adapter
- End-to-end: sample data -> discovery -> mapping -> generation -> adapter runs correctly

Done means: MappingConfig goes in, clean typed Python adapter comes out, adapter processes sample data and produces valid universal schema output, generated tests pass.

---

## Phase 5: Test Harness + Synthetic Insurers
**Spec:** docs/PHASE_5_SPEC.md
**Status:** [ ] Not started

What gets built:
- Synthetic Insurer A: Guidewire-style JSON (50+ claims with exposures, incidents, contacts, transactions)
- Synthetic Insurer B: ACORD XML (30+ claims with namespaces, custom extensions, missing optional fields)
- Synthetic Insurer C: Legacy CSV (40+ claims, pipe-delimited, cryptic field names, packed dates)
- Contract tests: adapter output matches universal schema
- Round-trip validation: all required fields populated, types correct, values in range
- Edge case generator: LLM produces adversarial inputs
- Test reporter: summary with pass/fail, field-level accuracy, coverage

Done means: all three synthetic insurers go through the full pipeline (discover -> map -> generate -> test), all contract tests pass, edge cases handled, test report generated.

---

## Phase 6: Drift Monitor + Alert System
**Spec:** docs/PHASE_6_SPEC.md
**Status:** [ ] Not started

What gets built:
- Schema monitor comparing incoming data vs expected schema
- Field-level drift detection (rename, remove, type change, new field, format change)
- Human-readable alert generation with proposed fix
- Fix proposer using LLM to suggest config update
- Approval workflow (proposed fix waits for human)
- Drift history log
- Simulated drift scenarios (rename field, change date format, add field, remove field)
- FastAPI endpoints for monitor operations

Done means: simulate schema changes on synthetic data, monitor detects them, alerts are human-readable, proposed fixes are correct, approval flow works, drift history is logged.
