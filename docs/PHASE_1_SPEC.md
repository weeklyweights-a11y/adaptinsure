# Phase 1: Universal Schema + Base Adapter Interface

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Nothing. This is the foundation. Everything else builds on this.

---

## What This Phase Delivers

The canonical insurance claims data model and the abstract adapter contract. After this phase, you have Pydantic models that can validate any insurance claim from any source, an error taxonomy for every failure mode, and a base adapter class that every generated adapter must implement.

Nothing in this phase talks to an LLM, parses files, or generates code. This is pure data modeling and validation logic.

---

## Step 1: Project Skeleton

Create the project structure, config, and dependencies.

What to create:
- requirements.txt with all dependencies pinned to specific versions: pydantic>=2.7, pydantic-settings>=2.2, fastapi>=0.111, uvicorn>=0.30, google-genai>=1.0, jinja2>=3.1, lxml>=5.2, pandas>=2.2, pyyaml>=6.0, jsonschema>=4.22, pytest>=8.2, pytest-asyncio>=0.23, httpx>=0.27, python-dotenv>=1.0, ruff>=0.4
- .env.example with placeholder for GEMINI_API_KEY and LOG_LEVEL=INFO
- .gitignore covering Python defaults (__pycache__, *.pyc, .pytest_cache, .ruff_cache, .env, generated/*.py except .gitkeep, dist/, build/, *.egg-info)
- src/__init__.py (empty)
- src/config.py — Settings class using pydantic-settings. Fields: gemini_api_key (str, default "" — optional in Phase 1, no LLM calls yet), log_level (str, default INFO), generated_adapters_dir (Path, default generated/). Load from .env file. Configure logging in a setup_logging() function using stdlib logging.
- generated/.gitkeep (empty file so git tracks the directory)

After this step:
- git commit: chore: initialize project skeleton with dependencies and config

### Step 1 Tests

No tests yet. Just verify: python -c "from src.config import Settings; print('ok')" runs without error.

### Step 1 Checklist
- [ ] requirements.txt exists with all deps pinned
- [ ] .env.example exists with GEMINI_API_KEY placeholder
- [ ] .gitignore covers all Python defaults and generated/*.py
- [ ] src/__init__.py exists
- [ ] src/config.py has Settings class loading from .env
- [ ] src/config.py has setup_logging() function
- [ ] generated/.gitkeep exists
- [ ] git commit done: chore: initialize project skeleton with dependencies and config

---

## Step 2: Enums

Create all enum types for the insurance domain.

What to create:
- src/schema/__init__.py (empty)
- src/schema/enums.py

All enums use StrEnum so they serialize to JSON as strings.

ClaimStatus — the lifecycle state of a claim
- Values: open, closed, reopened, denied, pending

ExposureStatus — the state of an exposure within a claim
- Values: open, closed

ExposureType — what kind of loss this exposure covers
- Values: vehicle_damage, bodily_injury, property_damage, med_pay, pip, um_uim, liability, cargo, other

ContactRole — what role a person/org plays on a claim
- Values: insured, claimant, witness, attorney, adjuster, vendor, other

TransactionType — the kind of financial movement
- Values: payment, recovery, reserve_set, reserve_change

TransactionStatus — where a transaction is in its lifecycle
- Values: pending, approved, posted, voided

LineOfBusiness — the insurance product line
- Values: personal_auto, commercial_auto, homeowners, commercial_property, general_liability, workers_comp, professional_liability, umbrella, inland_marine, other

LossCause — what caused the loss
- Values: collision, theft, fire, weather, water_damage, vandalism, slip_and_fall, product_liability, medical_malpractice, workplace_injury, other

After this step:
- git commit: schema: add all insurance domain enums

### Step 2 Tests

Create tests/test_schema.py (will be expanded in later steps).

Test that every enum:
- Has the expected number of values
- All values are strings (StrEnum)
- Can be created from string: ClaimStatus("open") works
- Invalid string raises ValueError: ClaimStatus("invalid") raises
- JSON serialization round-trips correctly: json.loads(json.dumps(status.value)) gives back the same value

### Step 2 Checklist
- [ ] src/schema/__init__.py exists
- [ ] src/schema/enums.py has all 8 enums
- [ ] Every enum uses StrEnum
- [ ] Every enum has the exact values listed above
- [ ] tests/test_schema.py exists with enum tests
- [ ] All tests pass: pytest tests/test_schema.py
- [ ] git commit done: schema: add all insurance domain enums

---

## Step 3: Address and Coverage Models

Create the reusable sub-models that other models depend on.

What to create in src/schema/models.py:

Address model:
- street_1: str — primary street address
- street_2: str or None, default None — apartment/suite/unit
- city: str
- state: str — two-letter state code for US, or full name for international
- postal_code: str — string not int (leading zeros matter: 07302)
- country: str, default "US" — ISO 3166-1 alpha-2

Coverage model:
- coverage_type: str — the name of the coverage (e.g. "Collision", "Bodily Injury Liability")
- limit: Decimal — coverage limit amount
- deductible: Decimal — deductible amount for this coverage
- premium: Decimal — premium for this specific coverage

Both models: strict mode, frozen (immutable after creation).

After this step:
- git commit: schema: add Address and Coverage models

### Step 3 Tests

Add to tests/test_schema.py:

Address tests:
- Valid US address creates successfully
- Valid international address (country not US) creates successfully
- Missing required field (city) raises ValidationError
- postal_code is string type (verify "07302" keeps its leading zero)

Coverage tests:
- Valid coverage creates successfully
- Negative limit raises ValidationError (add validator — limits must be >= 0)
- Negative deductible raises ValidationError
- Decimal precision is maintained (1234.56 stays as 1234.56, not 1234.5600000001)

### Step 3 Checklist
- [ ] src/schema/models.py exists with Address and Coverage
- [ ] Both models use strict mode and are frozen
- [ ] Decimal fields used for all monetary amounts
- [ ] postal_code is str type
- [ ] Tests added for Address and Coverage
- [ ] All tests pass
- [ ] git commit done: schema: add Address and Coverage models

---

## Step 4: Core Entity Models

Create the main insurance entity models. These are the heart of the universal schema.

What to add to src/schema/models.py:

Claim model:
- claim_id: str — unique identifier from source system
- claim_number: str — human-readable claim number
- status: ClaimStatus
- loss_date: datetime — when the loss occurred. Must be timezone-aware.
- reported_date: datetime — when the claim was reported (FNOL date). Must be >= loss_date.
- closed_date: datetime or None, default None — when claim was closed. If present, must be >= reported_date.
- loss_description: str — free-text description of what happened
- loss_cause: LossCause
- loss_location: Address
- line_of_business: LineOfBusiness
- policy_number: str
- policy_effective_date: datetime
- policy_expiration_date: datetime — must be > policy_effective_date
- total_incurred: Decimal, default 0 — must be >= 0
- total_paid: Decimal, default 0 — must be >= 0
- total_reserved: Decimal, default 0 — must be >= 0
- deductible: Decimal, default 0 — must be >= 0
- catastrophe_code: str or None, default None
- litigation_flag: bool, default False
- subrogation_flag: bool, default False
- fraud_flag: bool, default False
- adjuster_id: str or None, default None
- adjuster_name: str or None, default None
- created_at: datetime — when this record was created in AdaptInsure
- updated_at: datetime — when this record was last updated
- source_system: str — identifies which carrier/CMS this came from
- raw_data: dict — the original unmodified record as received. This is the escape hatch for data that doesn't map to the schema.
- exposures: list of Exposure, default empty list
- claimants: list of Claimant, default empty list
- transactions: list of Transaction, default empty list

Exposure model:
- exposure_id: str
- claim_id: str — must match parent claim
- exposure_type: ExposureType
- coverage_type: str
- status: ExposureStatus, default open
- reserved_amount: Decimal, default 0 — must be >= 0
- paid_amount: Decimal, default 0 — must be >= 0
- deductible_amount: Decimal, default 0 — must be >= 0
- claimant_id: str — the claimant this exposure is for

Claimant model:
- claimant_id: str
- claim_id: str
- role: ContactRole
- first_name: str
- last_name: str
- organization_name: str or None, default None
- email: str or None, default None
- phone: str or None, default None
- address: Address or None, default None
- date_of_birth: date or None, default None

Transaction model:
- transaction_id: str
- claim_id: str
- exposure_id: str or None, default None
- transaction_type: TransactionType
- amount: Decimal — can be positive (payment out) or negative (recovery in). But reserve_set and reserve_change must be >= 0.
- currency: str, default "USD" — ISO 4217 currency code, 3 uppercase letters
- transaction_date: datetime
- check_number: str or None, default None
- payee_name: str or None, default None
- status: TransactionStatus, default pending

PolicySnapshot model:
- policy_number: str
- carrier_name: str
- product_type: str
- effective_date: datetime
- expiration_date: datetime — must be > effective_date
- insured_name: str
- coverages: list of Coverage, default empty list
- premium: Decimal, default 0 — must be >= 0

After this step:
- git commit: schema: add Claim, Exposure, Claimant, Transaction, PolicySnapshot models

### Step 4 Tests

Add to tests/test_schema.py:

Claim tests:
- Valid claim with all required fields creates successfully
- Valid claim with all optional fields populated creates successfully
- Minimal claim (only required fields, all optionals as None/default) creates successfully
- reported_date before loss_date raises ValidationError
- closed_date before reported_date raises ValidationError
- policy_expiration_date before policy_effective_date raises ValidationError
- Negative total_paid raises ValidationError
- Negative total_reserved raises ValidationError
- Negative deductible raises ValidationError
- loss_date as naive datetime (no timezone) raises ValidationError
- Claim with exposures list containing valid Exposures creates successfully
- raw_data accepts any dict

Exposure tests:
- Valid exposure creates successfully
- Negative reserved_amount raises ValidationError
- Negative paid_amount raises ValidationError

Claimant tests:
- Valid claimant with person fields creates successfully
- Valid claimant with organization_name creates successfully
- Missing first_name raises ValidationError
- Missing last_name raises ValidationError

Transaction tests:
- Valid payment transaction creates successfully
- Valid recovery transaction creates successfully
- Currency code must be 3 uppercase letters — "usd" or "US" raises ValidationError
- reserve_set with negative amount raises ValidationError (reserves can't be negative)
- payment with negative amount is allowed (refunds exist)

PolicySnapshot tests:
- Valid policy creates successfully
- expiration_date before effective_date raises ValidationError
- Negative premium raises ValidationError
- Policy with coverages list creates successfully

### Step 4 Checklist
- [ ] Claim model has all fields listed above with correct types
- [ ] Exposure model has all fields with correct types
- [ ] Claimant model has all fields with correct types
- [ ] Transaction model has all fields with correct types
- [ ] PolicySnapshot model has all fields with correct types
- [ ] All cross-field validators work (date ordering, amount constraints)
- [ ] Timezone-aware datetimes enforced on all datetime fields
- [ ] Decimal used for all monetary fields — no floats anywhere
- [ ] All tests pass
- [ ] git commit done: schema: add Claim, Exposure, Claimant, Transaction, PolicySnapshot models

---

## Step 5: Custom Validators Module

Create reusable validation functions that the models use and that generated adapters will also use.

What to create in src/schema/validators.py:

validate_date_order(earlier, later, earlier_name, later_name) — raises ValueError if later < earlier. Used by Claim (loss_date <= reported_date <= closed_date) and PolicySnapshot (effective < expiration).

validate_non_negative(value, field_name) — raises ValueError if Decimal value < 0. Used for all monetary amounts.

validate_currency_code(code) — raises ValueError if not exactly 3 uppercase ASCII letters. Standard ISO 4217.

validate_timezone_aware(dt, field_name) — raises ValueError if datetime has no tzinfo. All dates in the system must be timezone-aware.

validate_claim_consistency(claim) — cross-field validation on a full Claim object:
- total_incurred should equal total_paid + total_reserved (warn if not, don't raise — source systems are often inconsistent)
- If status is "closed", closed_date should be present (warn if not)
- If litigation_flag is True, there should be at least one claimant with role "attorney" (warn if not)

The warn-don't-raise validators return a list of Warning objects (create a ValidationWarning dataclass with field_name, message, severity).

After this step:
- git commit: schema: add custom validators and ValidationWarning

### Step 5 Tests

Create or extend tests:

- validate_date_order with valid ordering passes silently
- validate_date_order with reversed dates raises ValueError with descriptive message
- validate_date_order with equal dates passes (same date is valid — claim can be reported same day as loss)
- validate_non_negative with 0 passes
- validate_non_negative with positive passes
- validate_non_negative with negative raises ValueError
- validate_currency_code with "USD" passes
- validate_currency_code with "EUR" passes
- validate_currency_code with "usd" raises (not uppercase)
- validate_currency_code with "US" raises (not 3 chars)
- validate_currency_code with "USDD" raises (4 chars)
- validate_timezone_aware with aware datetime passes
- validate_timezone_aware with naive datetime raises
- validate_claim_consistency returns empty warnings for a fully consistent claim
- validate_claim_consistency returns warning when total_incurred != total_paid + total_reserved
- validate_claim_consistency returns warning when status is closed but closed_date is None

### Step 5 Checklist
- [ ] src/schema/validators.py exists with all 5 validator functions
- [ ] ValidationWarning dataclass exists with field_name, message, severity
- [ ] Validators that should raise do raise with descriptive messages
- [ ] Consistency validators return warnings, not exceptions
- [ ] All tests pass
- [ ] git commit done: schema: add custom validators and ValidationWarning

---

## Step 6: Error Taxonomy

Create the custom exception hierarchy for the entire platform.

What to create in src/exceptions.py:

AdaptInsureError — base exception for the platform
- Fields: error_code (str), message (str), details (dict or None)
- String representation includes error_code and message

Subclasses (each inherits from AdaptInsureError):
- SchemaValidationError — data doesn't match universal schema. error_code prefix: SCHEMA_
- DiscoveryError — failed to analyze incoming data format. error_code prefix: DISC_
- MappingError — failed to map client fields to universal schema. error_code prefix: MAP_
- GenerationError — failed to generate adapter code. error_code prefix: GEN_
- TestHarnessError — generated adapter failed testing. error_code prefix: TEST_
- MonitorError — drift detection or alerting failed. error_code prefix: MON_
- LLMError — LLM call failed or returned invalid output. error_code prefix: LLM_
- ConfigError — configuration is missing or invalid. error_code prefix: CFG_

After this step:
- git commit: feat(schema): add error taxonomy with AdaptInsureError hierarchy

### Step 6 Tests

- AdaptInsureError can be raised and caught
- Each subclass can be raised and caught as its own type AND as AdaptInsureError
- error_code is stored correctly
- message is stored correctly
- details dict is stored correctly (including None default)
- str(error) includes both error_code and message

### Step 6 Checklist
- [ ] src/exceptions.py exists with AdaptInsureError and all 8 subclasses
- [ ] Every exception has error_code, message, details fields
- [ ] Every subclass is catchable as itself and as AdaptInsureError
- [ ] All tests pass
- [ ] git commit done: feat(schema): add error taxonomy with AdaptInsureError hierarchy

---

## Step 7: Base Adapter Abstract Class

Create the abstract base class that every generated adapter must implement.

What to create in src/schema/base_adapter.py:

BaseAdapter (ABC):

Properties (abstract):
- name: str — human-readable name of this adapter (e.g. "Guidewire Carrier A Adapter")
- version: str — semver string
- source_system: str — identifier for the source CMS/carrier
- supported_formats: list of str — what input formats this adapter handles (e.g. ["json"], ["xml"], ["csv"])

Methods (abstract):
- parse_raw(raw_input: str or bytes) -> list of dict — take raw input (file contents, API response body) and parse into list of raw records. Handle encoding, delimiters, namespaces. Raise DiscoveryError on failure.
- map_record(raw_record: dict) -> dict — take a single raw record and map it to the universal schema field names. Apply field mappings and transforms. Return a dict ready for Pydantic validation. Raise MappingError on failure.
- validate_record(mapped_record: dict) -> tuple of (Claim, list of ValidationWarning) — validate the mapped record against the universal schema. Return the validated Claim object and any warnings. Raise SchemaValidationError on failure.
- transform_batch(raw_input: str or bytes) -> TransformResult — convenience method that chains parse_raw -> map_record -> validate_record for every record. Implemented in the base class (not abstract) using the three methods above.

The transform_batch method is concrete (implemented in BaseAdapter). It iterates over parse_raw results, calls map_record on each, then validate_record on each. It collects results and errors separately. It does not stop on first error — it processes all records and returns both successes and failures.

Create a TransformResult dataclass to hold the output:
- successful: list of tuple (Claim, list of ValidationWarning)
- failed: list of tuple (dict, AdaptInsureError) — the raw record and the error
- total_records: int
- success_count: int
- failure_count: int

After this step:
- git commit: feat(schema): add BaseAdapter ABC and TransformResult

### Step 7 Tests

- BaseAdapter cannot be instantiated directly (it's abstract)
- A concrete subclass that implements all abstract methods can be instantiated
- transform_batch calls parse_raw, map_record, validate_record in sequence
- transform_batch collects successes and failures separately
- transform_batch continues processing after individual record failures
- TransformResult fields compute correctly (success_count + failure_count = total_records)

For testing: create a MockAdapter in conftest.py that implements BaseAdapter with hardcoded simple logic. Use it to test the transform_batch flow.

### Step 7 Checklist
- [ ] src/schema/base_adapter.py exists
- [ ] BaseAdapter is an ABC with all abstract properties and methods
- [ ] transform_batch is concrete and chains the three abstract methods
- [ ] TransformResult dataclass holds successes, failures, counts
- [ ] BaseAdapter cannot be instantiated
- [ ] MockAdapter in conftest.py works for testing
- [ ] transform_batch handles partial failures correctly
- [ ] All tests pass
- [ ] git commit done: feat(schema): add BaseAdapter ABC and TransformResult

---

## Step 8: Schema Package Exports and Final Validation

Clean up the schema package exports and run a full integration check.

What to do:
- Update src/schema/__init__.py to export all public models, enums, validators, base adapter, and result types. Anyone importing from src.schema should get everything they need.
- Create a tests/conftest.py with shared fixtures: a valid_claim fixture that creates a fully populated Claim with exposures, claimants, and transactions. A valid_address fixture. A valid_policy fixture. These will be reused across all future test files.
- Run the full test suite: pytest tests/ -v
- Run ruff check on all src/ files: ruff check src/
- Verify no import errors: python -c "from src.schema import Claim, Exposure, Claimant, Transaction, PolicySnapshot, Address, Coverage, ClaimStatus, ExposureType, ContactRole, BaseAdapter, TransformResult"

After this step:
- git commit: feat(schema): finalize schema package exports and shared test fixtures
- git tag: git tag -a phase-1-complete -m "Phase 1: Universal Schema + Base Adapter Interface"

### Step 8 Tests

- All imports from src.schema work
- The valid_claim fixture creates a Claim that passes validation
- The valid_claim fixture includes at least 2 exposures, 2 claimants, 3 transactions
- Serializing valid_claim to JSON and back produces an equal object
- Full test suite passes: pytest tests/ -v shows all green

### Step 8 Checklist
- [ ] src/schema/__init__.py exports all public types
- [ ] tests/conftest.py has valid_claim, valid_address, valid_policy fixtures
- [ ] Full pytest suite passes with 0 failures
- [ ] ruff check src/ passes with 0 errors
- [ ] All imports work from src.schema
- [ ] JSON round-trip serialization works for all models
- [ ] git commit done: feat(schema): finalize schema package exports and shared test fixtures
- [ ] git tag done: phase-1-complete

---

## Test Rules for This Phase

- Every test file starts with: from src.schema import ... (whatever is being tested)
- Test functions are named: test_<model>_<scenario>_<expected_outcome>
- Use pytest.raises(ValidationError) for tests that expect validation failures
- Use pytest.raises(ValueError) for tests that expect validator function failures
- Never hardcode dates — use datetime(2024, 1, 15, tzinfo=timezone.utc) style
- All monetary values in tests use Decimal("123.45") — never float
- Group tests by model using classes: class TestClaim, class TestExposure, etc.
- Each test class has at least: one happy path, one missing required field, one invalid value
- Fixtures go in conftest.py — not duplicated across test files

---

## What NOT to Build in This Phase

- No LLM integration
- No file parsing
- No code generation
- No API endpoints
- No CLI
- No frontend
- No Docker
- No database
- No sample data files yet

---

## Cursor Prompt

Give Cursor this exact prompt to start:

> Read .cursorrules, PROJECT.md, and docs/PHASE_1_SPEC.md. This is Phase 1. Nothing exists yet — you are starting from scratch. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create, what each contains, the order you will work in, and dependencies between files. Present the full plan and wait for my approval before writing any code.
