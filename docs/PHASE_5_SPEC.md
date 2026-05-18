# Phase 5: Test Harness + Synthetic Insurers

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phases 1-4 are complete. Universal schema, Discovery Engine, Mapping Engine, and Adapter Code Generator all exist. All tests pass including the end-to-end test from Phase 4.

---

## What This Phase Delivers

Three realistic synthetic insurer datasets that represent the real-world diversity of insurance data formats, plus a comprehensive automated test harness that validates generated adapters against these datasets. After this phase, you can demo the full pipeline: feed any of the three insurer formats, watch the system discover the schema, map the fields, generate an adapter, and correctly transform every claim into the universal format — with a test report showing pass/fail results.

This is the phase where the system proves it actually works on realistic data.

---

## Step 1: Synthetic Insurer A — Guidewire-Style JSON

Create a realistic dataset representing a carrier running Guidewire ClaimCenter with a modern REST API.

What to create in samples/guidewire_carrier/:

samples/guidewire_carrier/README.md:
- Carrier name: "Beacon Mutual Insurance"
- System: Guidewire ClaimCenter 10.x
- Format: JSON, REST API responses
- Field naming: camelCase (Guidewire convention)
- Date format: ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
- Currency: raw decimal numbers (no formatting)
- Enums: Guidewire typelist codes (e.g. "open", "closed" but also some like "CT:collision", "CT:theft" with category prefixes)

samples/guidewire_carrier/sample_claims.json:
- Array of 15 claim objects
- Each claim has nested exposures (1-3 per claim), contacts with roles, and transactions
- Field names follow Guidewire conventions:
  - claimNumber, lossDate, reportedDate, closedDate, claimState
  - lossCause, lossDescription, lossLocationAddress (nested: street, city, state, postalCode)
  - policyNumber, policyEffDate, policyExpDate
  - lineOfBusiness, totalIncurred, totalPaid, totalReserves, deductible
  - catastropheCode, litigationStatus, subrogationStatus, fraudIndicator
  - assignedAdjusterId, assignedAdjusterName
  - exposures: [{exposureId, exposureType, coverageType, status, reservedAmount, paidAmount, deductibleAmount, claimantId}]
  - contacts: [{contactId, claimId, role, firstName, lastName, orgName, email, phone, dateOfBirth, address}]
  - transactions: [{transactionId, claimId, exposureId, type, amount, currency, transactionDate, checkNumber, payeeName, status}]
- Claims should cover diverse scenarios:
  - Claims 1-3: Auto collision claims (vehicle damage + bodily injury exposures)
  - Claims 4-6: Homeowners claims (property damage — fire, water, weather)
  - Claims 7-8: Commercial GL claims (slip and fall, product liability)
  - Claim 9: Workers comp claim
  - Claim 10: Closed claim with closed_date and full payment history
  - Claim 11: Denied claim with status "denied"
  - Claim 12: Claim with litigation flag and attorney contact
  - Claim 13: Claim with subrogation recovery transactions
  - Claim 14: Catastrophe claim with CAT code
  - Claim 15: Minimal claim — only required fields, everything else null/empty
- Amounts should be realistic: deductibles $500-$5,000, reserves $1,000-$500,000, payments varying
- Dates should span 2023-2025
- Use realistic names, addresses (US cities/states), policy numbers

samples/guidewire_carrier/api_spec.json:
- A simplified OpenAPI 3.0 spec describing the claims endpoint
- Defines the Claim schema with all properties, types, descriptions
- Defines nested schemas for Exposure, Contact, Transaction, Address
- Includes enum definitions for claimState, exposureType, lossCause, contactRole, transactionType
- This gives the Discovery Engine a second input to work with — API documentation in addition to sample data

After this step:
- git commit: feat(samples): add Guidewire-style synthetic insurer dataset (15 claims)

### Step 1 Tests

No automated tests for sample data files — they are the test data. Manual verification:
- [ ] JSON is valid (python -c "import json; json.load(open('samples/guidewire_carrier/sample_claims.json'))")
- [ ] 15 claims present
- [ ] All required fields present on every claim
- [ ] Nested exposures, contacts, transactions present
- [ ] Date formats are ISO 8601
- [ ] Amounts are numeric (not strings)
- [ ] Diverse claim types covered (auto, homeowners, GL, WC)
- [ ] OpenAPI spec is valid JSON

### Step 1 Checklist
- [ ] samples/guidewire_carrier/README.md describes the carrier
- [ ] samples/guidewire_carrier/sample_claims.json has 15 diverse claims
- [ ] samples/guidewire_carrier/api_spec.json has valid OpenAPI spec
- [ ] All JSON files are valid
- [ ] Claims cover diverse scenarios (10+ different variations)
- [ ] Amounts are realistic for insurance
- [ ] git commit done: feat(samples): add Guidewire-style synthetic insurer dataset (15 claims)

---

## Step 2: Synthetic Insurer B — ACORD XML

Create a dataset representing a carrier that exports claims data in ACORD P&C XML format with custom extensions and inconsistencies.

What to create in samples/acord_carrier/:

samples/acord_carrier/README.md:
- Carrier name: "Heritage National Group"
- System: Custom CMS with ACORD XML export
- Format: XML, ACORD P&C namespace
- Field naming: PascalCase ACORD element names (ClaimsSvcRq, ClaimsOccurrence, LossDt, etc.)
- Date format: Mixed — some ISO 8601, some MM/DD/YYYY, some YYYYMMDD (this is realistic — ACORD says ISO but carriers deviate)
- Currency: string with dollar sign ("$1,234.56") in some fields, raw decimal in others
- Enums: ACORD type codes (some standard, some carrier-specific extensions)
- Quirks that make this harder than the Guidewire set:
  - ACORD namespace on root element but not consistently on children
  - Some fields use attributes instead of text content (<Amount CurCd="USD">1234.56</Amount>)
  - Missing optional fields on some claims (no catastrophe code, no fraud flag)
  - Custom extension elements not in ACORD standard (carrier-specific fields like <InternalRefNum>, <HandlerTeam>)
  - Comments in XML

samples/acord_carrier/sample_claims.xml:
- XML document with ACORD-style structure
- 12 claims wrapped in a ClaimsSvcRq root element
- Structure follows ACORD P&C patterns:
  - ClaimsSvcRq (root)
    - ClaimsOccurrence (one per claim)
      - ClaimsOccurrenceInfo
        - ClaimNumber
        - LossDt (date of loss)
        - ReportedDt (FNOL date)
        - ClaimStatusCd (open, closed, etc.)
        - LOBCd (line of business code)
        - LossDesc
        - CatastropheCd
      - Policy
        - PolicyNumber
        - EffectiveDt
        - ExpirationDt
        - ContractTerm
      - ClaimsParty (repeating — one per involved party)
        - ClaimsPartyInfo
          - PartyRoleCd (insured, claimant, witness, etc.)
          - PersonName (GivenName, Surname)
          - CommunicationsInfo (PhoneNumber, EmailAddr)
          - Address (Addr1, City, StateProvCd, PostalCode)
      - ClaimsPayment (repeating)
        - PaymentAmt (with CurCd attribute)
        - PaymentDt
        - PaymentTypeCd
        - CheckNumber
        - PayeeName
      - LossLocation
        - Address (Addr1, City, StateProvCd, PostalCode, CountryCd)
      - Coverage (repeating)
        - CoverageCd
        - CoverageDesc
        - DeductibleAmt
        - LimitAmt
        - ReserveAmt
- Claims cover:
  - Claims 1-4: Auto claims with ACORD auto-specific elements
  - Claims 5-7: Property claims with ACORD property elements
  - Claims 8-9: Liability claims
  - Claim 10: Claim with mixed date formats (ISO on some fields, MM/DD/YYYY on others)
  - Claim 11: Claim with custom extension elements
  - Claim 12: Minimal claim — bare minimum ACORD structure

samples/acord_carrier/schema.xsd:
- A simplified XSD schema for the ACORD-like structure
- Defines element types, required vs optional, enumerations
- Not a full ACORD XSD (those are proprietary) but representative enough for discovery

After this step:
- git commit: feat(samples): add ACORD XML synthetic insurer dataset (12 claims)

### Step 2 Tests

Manual verification:
- [ ] XML is well-formed (python -c "from lxml import etree; etree.parse('samples/acord_carrier/sample_claims.xml')")
- [ ] 12 claims present
- [ ] ACORD-style element naming used
- [ ] Mixed date formats present (at least 2 different formats across the dataset)
- [ ] Currency with $ sign present on some fields
- [ ] Custom extension elements present
- [ ] Attributes used for some values (CurCd, etc.)
- [ ] XSD is valid

### Step 2 Checklist
- [ ] samples/acord_carrier/README.md describes the carrier and its quirks
- [ ] samples/acord_carrier/sample_claims.xml has 12 claims in ACORD structure
- [ ] samples/acord_carrier/schema.xsd has simplified ACORD schema
- [ ] Mixed date formats present
- [ ] Currency formatting inconsistencies present
- [ ] Custom extension elements present
- [ ] All XML is well-formed
- [ ] git commit done: feat(samples): add ACORD XML synthetic insurer dataset (12 claims)

---

## Step 3: Synthetic Insurer C — Legacy Mainframe CSV

Create a dataset representing a carrier that does nightly batch exports from a COBOL-era mainframe.

What to create in samples/legacy_carrier/:

samples/legacy_carrier/README.md:
- Carrier name: "Consolidated Mutual of Ohio"
- System: AS/400 mainframe, COBOL-based claims system (installed 1994)
- Format: Pipe-delimited flat file, nightly batch export
- Field naming: Uppercase, abbreviated, max 10 chars (mainframe convention): CLM_NBR, DT_OF_LSS, RPTD_DT, CLM_STS, CLMNT_FST, CLMNT_LST, etc.
- Date format: YYYYMMDD as 8-digit integer (20240115 not 2024-01-15)
- Currency: cents as integer (123456 means $1,234.56) — some fields. Others are formatted "$1,234.56" string. Inconsistent because different batch jobs wrote different fields.
- Enums: Single-character or 2-3 character codes (O=open, C=closed, D=denied, R=reopened, P=pending)
- Booleans: Y/N
- Null handling: Empty string for missing values, or literal "NULL" string on some fields
- Encoding: latin-1 (not UTF-8)
- Quirks:
  - No nested data — everything is flat. Exposures, contacts, and transactions are in separate files
  - Header row uses abbreviated names that don't match any documentation
  - Some rows have trailing pipes
  - One field has values that look like dates but are actually policy numbers (YYYYNNNNN format)
  - Amount fields inconsistently formatted (some cents-as-integer, some dollar strings)

samples/legacy_carrier/claims.csv:
- Pipe-delimited (not comma)
- 20 claim records
- Header row: CLM_NBR|DT_OF_LSS|RPTD_DT|CLS_DT|CLM_STS|LSS_DESC|LSS_CAUSE|LOB|POL_NBR|POL_EFF|POL_EXP|TOT_INCR|TOT_PD|TOT_RSV|DED_AMT|CAT_CD|LIT_FLG|SUBR_FLG|FRD_FLG|ADJ_ID|ADJ_NM|LSS_ST1|LSS_CITY|LSS_ST|LSS_ZIP|SRC_SYS
- Date fields as YYYYMMDD integers
- Amount fields in cents (no decimal point): 150000 means $1,500.00
- Status as single chars: O, C, D, R, P
- Flags as Y/N
- Encoding: latin-1
- Some empty fields, some "NULL" literal strings
- Trailing whitespace on some fields

samples/legacy_carrier/exposures.csv:
- Pipe-delimited
- Header: EXP_ID|CLM_NBR|EXP_TP|COV_TP|EXP_STS|RSV_AMT|PD_AMT|DED_AMT|CLMNT_ID
- 35 exposure records across the 20 claims
- Amount fields in cents

samples/legacy_carrier/contacts.csv:
- Pipe-delimited
- Header: CNTCT_ID|CLM_NBR|ROLE_CD|FST_NM|LST_NM|ORG_NM|EMAIL|PHONE|DOB|ADDR1|CITY|STATE|ZIP
- 40 contact records
- DOB as YYYYMMDD
- ROLE_CD: I=insured, C=claimant, W=witness, A=attorney, J=adjuster, V=vendor

samples/legacy_carrier/transactions.csv:
- Pipe-delimited
- Header: TXN_ID|CLM_NBR|EXP_ID|TXN_TP|AMT|CURR|TXN_DT|CHK_NBR|PAYEE|TXN_STS
- 50 transaction records
- TXN_TP: P=payment, R=recovery, S=reserve_set, C=reserve_change
- TXN_STS: P=pending, A=approved, T=posted, V=voided
- AMT in cents

samples/legacy_carrier/data_dictionary.md:
- A markdown table that a business analyst wrote 5 years ago
- Partially complete — covers claims.csv fields but not all of them
- Some descriptions are vague ("CLM_STS: claim status code")
- Some fields not listed at all
- Format column present but not always filled in
- This tests the data dictionary parser from Phase 2

After this step:
- git commit: feat(samples): add legacy mainframe synthetic insurer dataset (20 claims, 4 files)

### Step 3 Tests

Manual verification:
- [ ] All CSV files parse without error (python -c "import csv; list(csv.reader(open('samples/legacy_carrier/claims.csv'), delimiter='|'))")
- [ ] claims.csv has 20 data rows plus header
- [ ] exposures.csv has 35 rows
- [ ] contacts.csv has 40 rows
- [ ] transactions.csv has 50 rows
- [ ] Pipe delimiter used consistently
- [ ] Date fields are YYYYMMDD integers
- [ ] Amount fields are cents-as-integer
- [ ] Status codes are single characters
- [ ] Some empty fields and "NULL" strings present
- [ ] data_dictionary.md is valid markdown with a table
- [ ] Encoding is latin-1 (verify with: python -c "open('samples/legacy_carrier/claims.csv', encoding='latin-1').read()")

### Step 3 Checklist
- [ ] samples/legacy_carrier/README.md describes the carrier and all its quirks
- [ ] samples/legacy_carrier/claims.csv — 20 pipe-delimited claims
- [ ] samples/legacy_carrier/exposures.csv — 35 exposure records
- [ ] samples/legacy_carrier/contacts.csv — 40 contact records
- [ ] samples/legacy_carrier/transactions.csv — 50 transaction records
- [ ] samples/legacy_carrier/data_dictionary.md — partial field documentation
- [ ] All quirks present (YYYYMMDD dates, cents amounts, Y/N booleans, single-char codes, NULL strings, latin-1)
- [ ] git commit done: feat(samples): add legacy mainframe synthetic insurer dataset (20 claims, 4 files)

---

## Step 4: Contract Test Framework

Build the automated test framework that validates generated adapters produce correct output.

What to create in src/testing/__init__.py (empty) and src/testing/contract_tests.py:

ContractTestRunner class:
- method: run(adapter: BaseAdapter, raw_input: str or bytes, expected_count: int or None = None) -> ContractTestResult
- Runs the adapter's transform_batch on the raw input
- For each successful Claim in the result, validates:
  - Schema compliance: the Claim object was accepted by Pydantic (this is guaranteed by transform_batch, but double-check)
  - Required fields populated: claim_id, claim_number, status, loss_date, reported_date, loss_description, source_system are not None/empty
  - Type correctness: loss_date is timezone-aware datetime, total_paid is Decimal, status is valid ClaimStatus value
  - Date sanity: loss_date is not in the future, reported_date >= loss_date, closed_date >= reported_date (if present)
  - Amount sanity: total_paid >= 0, total_reserved >= 0, deductible >= 0 (warn if total_incurred != total_paid + total_reserved)
  - Referential integrity: every exposure.claim_id matches parent claim.claim_id, every claimant.claim_id matches, every transaction.claim_id matches
  - Enum validity: all enum fields contain valid enum values
- Collects results per check per claim

ContractTestResult model:
- total_claims: int
- passed_claims: int — claims where all checks passed
- failed_claims: int
- total_checks: int — total individual checks run
- passed_checks: int
- failed_checks: int
- failures: list of ContractFailure — detailed failure info
- warnings: list of str
- pass_rate: float — passed_checks / total_checks

ContractFailure model:
- claim_id: str or None
- claim_number: str or None
- check_name: str — which check failed (e.g. "required_field:loss_date", "date_sanity:reported_before_loss", "type_correctness:total_paid")
- expected: str — what was expected
- actual: str — what was found
- severity: str — error or warning

After this step:
- git commit: feat(testing): add ContractTestRunner for adapter validation

### Step 4 Tests

Create a mock adapter that returns known Claim objects:
- All checks pass on a valid Claim -> ContractTestResult with 0 failures
- Missing required field (loss_description empty) -> failure with check_name "required_field:loss_description"
- Future loss_date -> failure with check_name "date_sanity:future_loss_date"
- reported_date before loss_date -> failure
- Negative total_paid -> failure
- Invalid enum value -> failure (this shouldn't happen with Pydantic but test the check)
- Exposure with mismatched claim_id -> failure with check_name "referential_integrity:exposure_claim_id"
- Mix of passing and failing claims -> correct counts in result
- pass_rate computed correctly

### Step 4 Checklist
- [ ] src/testing/__init__.py exists
- [ ] src/testing/contract_tests.py has ContractTestRunner, ContractTestResult, ContractFailure
- [ ] Checks: required fields, type correctness, date sanity, amount sanity, referential integrity, enum validity
- [ ] Results tracked per claim per check
- [ ] pass_rate computed correctly
- [ ] All tests pass
- [ ] git commit done: feat(testing): add ContractTestRunner for adapter validation

---

## Step 5: Round-Trip Validator

Verify that data survives the full round trip: raw input -> adapter -> universal schema -> serialized output without data loss.

What to create in src/testing/roundtrip.py:

RoundTripValidator class:
- method: validate(adapter: BaseAdapter, raw_input: str or bytes) -> RoundTripResult
- Flow:
  1. Parse raw input with adapter.parse_raw() -> list of raw records
  2. For each raw record:
     a. Map with adapter.map_record() -> mapped dict
     b. Validate with adapter.validate_record() -> Claim object
     c. Serialize the Claim back to dict (claim.model_dump())
     d. Compare: for every field in the original raw record that has a mapping, verify the value survived the round trip (accounting for transforms — "01/15/2024" becomes a datetime, but the date should be January 15 2024)
  3. Track field-level survival: which fields made it through, which were lost, which were transformed correctly

RoundTripResult model:
- total_records: int
- total_fields_checked: int — total field comparisons across all records
- fields_survived: int — fields where value round-tripped correctly
- fields_lost: int — fields present in source but missing in output
- fields_transformed: int — fields present in both but value changed (due to intentional transforms)
- field_survival_rate: float — fields_survived / total_fields_checked
- lost_fields: list of LostField — details on what was lost

LostField model:
- record_index: int
- source_field: str
- source_value: str
- reason: str — why it was lost (unmapped, transform failed, validation rejected)

After this step:
- git commit: feat(testing): add RoundTripValidator for data survival checking

### Step 5 Tests

- Valid data round-trips completely -> field_survival_rate 1.0
- Date field transforms correctly (source "01/15/2024" -> datetime 2024-01-15) counted as survived, not lost
- Currency field transforms correctly ("$1,234.56" -> Decimal(1234.56)) counted as survived
- Unmapped source field -> counted as lost with reason "unmapped"
- Field that fails transform -> counted as lost with reason "transform failed"
- Empty input -> total_records 0, field_survival_rate 0.0

### Step 5 Checklist
- [ ] src/testing/roundtrip.py has RoundTripValidator, RoundTripResult, LostField
- [ ] Tracks field-level survival through the pipeline
- [ ] Correctly identifies transformed values as survived (not lost)
- [ ] Reports lost fields with reasons
- [ ] All tests pass
- [ ] git commit done: feat(testing): add RoundTripValidator for data survival checking

---

## Step 6: Edge Case Generator

Use Gemini to generate adversarial test inputs that stress-test the adapters.

What to create in src/testing/edge_cases.py:

EdgeCaseGenerator class:
- Dependencies: LLMClient (Gemini API)
- async method: generate(adapter_name: str, source_format: str, sample_record: dict or str, count: int = 20) -> list of EdgeCase
- Sends the sample record to Gemini with prompt:
  - You are a QA engineer testing an insurance claims data adapter
  - Given this sample record from a {source_format} source, generate {count} adversarial test cases
  - Categories to cover:
    - Null/empty values: fields that are None, empty string, whitespace-only
    - Boundary dates: date of loss in the future, date of loss = Jan 1 1900, reported date 10 years after loss
    - Boundary amounts: zero, negative, extremely large (999999999.99), very small (0.01)
    - Encoding issues: Unicode characters in names (accents, CJK), special chars in descriptions
    - Format violations: date in wrong format, amount with wrong currency symbol, enum value not in expected list
    - Missing required fields: each required field missing one at a time
    - Extra fields: fields not in the expected schema
    - Type mismatches: string where number expected, number where string expected
    - Duplicate IDs: same claim_id appearing twice
    - Referential integrity violations: exposure referencing non-existent claim
  - Each test case should specify: the mutated record, what was changed, and whether the adapter should handle it gracefully or raise an error
- Validate Gemini output against Pydantic model
- Temperature 0.2 (slightly creative for adversarial scenarios)

EdgeCase model:
- name: str — short description (e.g. "future_loss_date", "negative_payment", "unicode_claimant_name")
- category: str — which category from above
- mutated_record: dict or str — the adversarial input
- mutation_description: str — what was changed from the original
- expected_behavior: str — "should_succeed" (adapter handles gracefully) or "should_fail" (adapter should raise error) or "should_warn" (succeed with warning)

After this step:
- git commit: feat(testing): add EdgeCaseGenerator with Gemini-powered adversarial inputs

### Step 6 Tests

Mock Gemini API:
- Generates requested number of edge cases (count=10 -> 10 cases returned)
- Each EdgeCase has name, category, mutated_record, mutation_description, expected_behavior
- Categories are diverse (not all the same type)
- expected_behavior is one of the valid values
- Gemini returns invalid JSON -> retries once, then raises LLMError
- Edge cases based on JSON format produce dict records
- Edge cases based on CSV format produce string records

### Step 6 Checklist
- [ ] src/testing/edge_cases.py has EdgeCaseGenerator and EdgeCase
- [ ] Generates diverse adversarial inputs across all categories
- [ ] Uses Gemini API (mocked in tests)
- [ ] Temperature 0.2
- [ ] Each case has expected_behavior
- [ ] All tests pass
- [ ] git commit done: feat(testing): add EdgeCaseGenerator with Gemini-powered adversarial inputs

---

## Step 7: Test Reporter

Generate a clean test report summarizing all results.

What to create in src/testing/reporter.py:

TestReporter class:
- method: generate_report(contract_result: ContractTestResult, roundtrip_result: RoundTripResult, edge_case_results: list of tuple(EdgeCase, str) or None = None) -> TestReport
  - Combine all results into a single report
  - The edge_case_results is a list of (EdgeCase, outcome) where outcome is "passed", "failed_expected" (failed as expected), or "failed_unexpected" (should have succeeded but didn't, or should have failed but didn't)

TestReport model:
- adapter_name: str
- generated_at: datetime
- overall_status: str — "pass" (all critical checks passed), "warn" (passed with warnings), "fail" (critical failures)
- contract_summary: ContractTestResult
- roundtrip_summary: RoundTripResult
- edge_case_summary: EdgeCaseSummary or None
- total_checks: int
- total_passed: int
- total_failed: int
- critical_failures: list of str — human-readable descriptions of critical failures
- recommendations: list of str — suggested fixes

EdgeCaseSummary model:
- total_cases: int
- passed: int — edge cases that behaved as expected
- failed_unexpected: int — edge cases that didn't behave as expected
- categories_tested: list of str
- worst_category: str or None — category with most unexpected failures

method: format_report(report: TestReport) -> str
- Produces a clean, human-readable text report
- Sections: Overview, Contract Tests, Round-Trip Validation, Edge Cases (if run), Critical Failures, Recommendations
- Includes pass/fail counts, rates, and specific failure details
- Suitable for printing to console or saving to file

method: save_report(report: TestReport, output_path: Path) -> None
- Save the formatted report as a text file
- Also save the raw TestReport as JSON alongside it

After this step:
- git commit: feat(testing): add TestReporter for comprehensive test summaries

### Step 7 Tests

- Report with all passing results -> overall_status "pass"
- Report with warnings but no critical failures -> overall_status "warn"
- Report with critical failures -> overall_status "fail"
- format_report produces non-empty string with all sections
- save_report writes both .txt and .json files
- Edge case summary computes worst_category correctly
- Recommendations populated for common failure patterns (e.g. "3 date sanity checks failed — verify date format transform")
- Report with no edge cases (None) -> edge_case_summary is None, report still formats correctly

### Step 7 Checklist
- [ ] src/testing/reporter.py has TestReporter, TestReport, EdgeCaseSummary
- [ ] Combines contract, roundtrip, and edge case results
- [ ] overall_status logic correct (pass/warn/fail)
- [ ] format_report produces clean human-readable output
- [ ] save_report writes .txt and .json
- [ ] Recommendations generated for common failures
- [ ] All tests pass
- [ ] git commit done: feat(testing): add TestReporter for comprehensive test summaries

---

## Step 8: Full Pipeline Validation — All Three Insurers

Run the complete pipeline on all three synthetic insurers and generate test reports.

What to create in tests/test_full_pipeline.py:

Three test functions (or one parametrized test), each doing:

1. Load sample data from samples/{insurer}/
2. Run DiscoveryEngine.discover() -> ClientProfile
3. Assert: correct format detected, reasonable field count, no critical errors
4. Run MappingEngine.map() -> MappingConfig
5. Assert: majority of fields mapped, no critical gaps on required fields
6. Run GeneratorEngine.generate() -> GenerationResult
7. Assert: syntax_valid is True
8. Load generated adapter via AdapterRegistry
9. Instantiate adapter
10. Run ContractTestRunner on sample data
11. Assert: pass_rate >= 0.9 (at least 90% of checks pass)
12. Run RoundTripValidator on sample data
13. Assert: field_survival_rate >= 0.85 (at least 85% of mapped fields survive round-trip)
14. Run EdgeCaseGenerator (mocked Gemini) to produce edge cases
15. Run each edge case through the adapter, compare outcome to expected_behavior
16. Run TestReporter to generate report
17. Assert: overall_status is "pass" or "warn" (not "fail")
18. Save report to tests/reports/{insurer_name}_report.txt
19. Clean up generated adapter files

test_full_pipeline_guidewire:
- Uses samples/guidewire_carrier/sample_claims.json
- Expected: high confidence mappings (mostly direct matches), high pass rate
- This is the "easy" case — modern format, clear field names

test_full_pipeline_acord:
- Uses samples/acord_carrier/sample_claims.xml
- Expected: mix of direct and semantic matches, some transform complexity (mixed dates, currency formatting)
- Medium difficulty

test_full_pipeline_legacy:
- Uses samples/legacy_carrier/claims.csv (and the other CSV files)
- Expected: heavy reliance on semantic matching, many transforms (YYYYMMDD dates, cents-to-dollars, single-char enums)
- This is the hard case — if this works, the system works
- Note: legacy carrier has separate files for exposures, contacts, transactions. The adapter needs to handle this — either by processing each file separately or by joining them on CLM_NBR. Document the approach in the test.

After this step:
- git commit: test: add full pipeline validation for all three synthetic insurers
- git tag: git tag -a phase-5-complete -m "Phase 5: Test Harness + Synthetic Insurers"

### Step 8 Tests

This IS the test suite. Acceptance criteria:
- All three insurer pipelines complete without unhandled exceptions
- Guidewire: pass_rate >= 0.95, field_survival_rate >= 0.90
- ACORD: pass_rate >= 0.90, field_survival_rate >= 0.85
- Legacy: pass_rate >= 0.85, field_survival_rate >= 0.80
- Three test reports generated in tests/reports/
- Overall status for each is "pass" or "warn"
- Generated adapter files cleaned up after tests

### Step 8 Checklist
- [ ] tests/test_full_pipeline.py exists with three test functions
- [ ] Guidewire pipeline passes with >= 0.95 pass rate
- [ ] ACORD pipeline passes with >= 0.90 pass rate
- [ ] Legacy pipeline passes with >= 0.85 pass rate
- [ ] Test reports generated and saved
- [ ] Generated files cleaned up
- [ ] Full test suite passes: pytest tests/ -v — all green
- [ ] ruff check src/ passes
- [ ] git commit done: test: add full pipeline validation for all three synthetic insurers
- [ ] git tag done: phase-5-complete

---

## Test Rules for This Phase

- Mock Gemini API in all tests — never make real API calls
- Sample data files are the test data — don't duplicate them in test fixtures
- Use pathlib.Path for all file paths
- Test reports go to tests/reports/ (create directory if needed)
- Clean up generated adapter files after each test (use tmp_path or explicit cleanup)
- The full pipeline tests are integration tests — they touch multiple modules. Keep them in a separate file (test_full_pipeline.py) from unit tests.
- If a pipeline test fails, the failure message should clearly indicate which step failed (discovery, mapping, generation, contract testing, round-trip, or edge cases)

---

## What NOT to Build in This Phase

- No API endpoints — those come later
- No monitoring — that's Phase 6
- No UI
- No real insurer data — everything is synthetic
- No performance benchmarks (timing, memory) — focus on correctness

---

## Cursor Prompt

> Read .cursorrules, PROJECT.md, and docs/PHASE_5_SPEC.md. Phases 1-4 are complete. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create, what each contains, the order, and dependencies. Wait for my approval.
