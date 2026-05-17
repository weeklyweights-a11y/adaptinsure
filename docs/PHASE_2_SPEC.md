# Phase 2: Discovery Engine

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phase 1 is complete. All Pydantic models, enums, validators, BaseAdapter, and error taxonomy exist. All Phase 1 tests pass.

---

## What This Phase Delivers

The Discovery Engine — the system that takes raw data from any insurer (JSON, XML, CSV, or a data dictionary document) and produces a structured ClientProfile describing exactly what that data looks like. Field names, types, sample values, nesting structure, format patterns, and insurance domain annotations.

This phase introduces the first LLM integration. The LLM analyzes parsed data structures and adds semantic understanding — it recognizes that a field called "dt_of_lss" probably means "date of loss" and that "excess_amt" means "deductible amount."

---

## Step 1: ClientProfile Model

Create the output model for the Discovery Engine — the structured description of a client's data.

What to create in src/discovery/profile.py:

FieldInfo model — describes a single field in the client's data:
- source_name: str — the field name as it appears in the client's data (e.g. "lossDate", "DT_OF_LSS", "ClaimLossDate")
- inferred_type: str — what data type this field appears to be: string, integer, decimal, boolean, date, datetime, array, object, null, unknown
- sample_values: list of str — up to 5 sample values from the data (as strings for uniformity)
- nullable: bool — whether any null/empty values were observed
- format_pattern: str or None — detected pattern (e.g. "MM/DD/YYYY", "YYYY-MM-DD", "ISO 8601", "YYYYMMDD packed", "$#,###.##")
- description: str or None — from data dictionary or API docs if available
- insurance_annotation: str or None — LLM-inferred insurance meaning (e.g. "date of loss", "deductible amount", "claimant last name"). Filled by the LLM analyzer, not the parser.
- confidence: float — 0.0 to 1.0, how confident the system is in the type/annotation inference
- nesting_path: str or None — for nested data, the dot-path to this field (e.g. "claim.exposures[].amount")

ClientProfile model — the complete description of a client's data:
- client_name: str — identifier for this client/carrier
- source_format: str — json, xml, csv, fixed_width, unknown
- detected_encoding: str — utf-8, latin-1, etc.
- total_records_sampled: int — how many records were analyzed
- total_fields_detected: int
- fields: list of FieldInfo
- nested_structures: list of str — names of nested objects/arrays detected (e.g. ["exposures", "contacts", "transactions"])
- notes: list of str — any observations (e.g. "ACORD namespace detected", "Guidewire-style camelCase naming", "No header row detected")
- raw_sample: dict or str — a single raw record for reference
- created_at: datetime
- warnings: list of str — any issues found during discovery (e.g. "3 fields have no sample values", "mixed date formats detected")

After this step:
- git commit: feat(discovery): add ClientProfile and FieldInfo models

### Step 1 Tests

Create tests/test_discovery.py:

- FieldInfo with all required fields creates successfully
- FieldInfo with sample_values list stores correctly
- FieldInfo confidence must be between 0.0 and 1.0 — values outside raise ValidationError
- ClientProfile with valid fields list creates successfully
- ClientProfile with empty fields list creates successfully (some data might have no parseable fields)
- ClientProfile total_fields_detected matches len(fields)

### Step 1 Checklist
- [ ] src/discovery/__init__.py exists
- [ ] src/discovery/profile.py has FieldInfo and ClientProfile models
- [ ] Both models use Pydantic with proper types
- [ ] confidence field is constrained to 0.0-1.0
- [ ] Tests written and passing
- [ ] git commit done: feat(discovery): add ClientProfile and FieldInfo models

---

## Step 2: Format Detector

Create the entry point that looks at raw input and figures out what format it is.

What to create in src/discovery/parsers/__init__.py:

detect_format(raw_input: str or bytes) -> str function:
- Returns one of: "json", "xml", "csv", "fixed_width", "unknown"
- Detection logic (in order):
  1. Strip leading whitespace
  2. If starts with "{" or "[" — try json.loads(). If succeeds, return "json"
  3. If starts with "<" or "<?xml" — return "xml"
  4. Try csv.Sniffer().sniff() on first 8192 bytes. If it detects a delimiter, return "csv"
  5. If lines have consistent character-position patterns (all lines same length, or consistent column widths) — return "fixed_width"
  6. Return "unknown"
- Handle bytes input by decoding with chardet or falling back to utf-8 then latin-1
- Raise DiscoveryError if input is empty or unreadable

After this step:
- git commit: feat(discovery): add format auto-detection

### Step 2 Tests

- JSON object detected: '{"claim_id": "123"}' returns "json"
- JSON array detected: '[{"claim_id": "123"}]' returns "json"
- XML detected: '<?xml version="1.0"?><claims></claims>' returns "xml"
- XML without declaration detected: '<claims><claim id="1"/></claims>' returns "xml"
- CSV detected: 'id,name,date\n1,John,2024-01-01\n' returns "csv"
- Pipe-delimited detected: 'id|name|date\n1|John|2024-01-01\n' returns "csv" (csv module detects pipe as delimiter)
- Empty input raises DiscoveryError
- Whitespace-only input raises DiscoveryError
- Binary garbage returns "unknown"
- JSON with leading whitespace still detected: '  {"claim_id": "123"}' returns "json"

### Step 2 Checklist
- [ ] src/discovery/parsers/__init__.py has detect_format function
- [ ] Handles JSON, XML, CSV detection correctly
- [ ] Handles bytes input with encoding detection
- [ ] Raises DiscoveryError on empty/unreadable input
- [ ] All tests pass
- [ ] git commit done: feat(discovery): add format auto-detection

---

## Step 3: JSON Parser

Parse JSON data (API responses, OpenAPI specs) and extract field information.

What to create in src/discovery/parsers/json_parser.py:

parse_json(raw_input: str) -> list of FieldInfo function:
- Parse the JSON string
- If it's an array of objects, analyze the objects to build field list
- If it's a single object, treat it as a one-record sample
- For each field found:
  - Determine source_name (the key)
  - Infer type from Python type (str->string, int->integer, float->decimal, bool->boolean, list->array, dict->object, None->null)
  - Collect up to 5 unique sample values across all records
  - Detect nullable (any record has None for this field)
  - Detect date patterns in string values (try common formats: ISO 8601, MM/DD/YYYY, YYYY-MM-DD, etc.)
  - For nested objects/arrays, recurse and include nesting_path (e.g. "exposures[].amount")
- Return flat list of FieldInfo (nested fields flattened with dot-path notation)

parse_openapi_spec(spec_input: str) -> list of FieldInfo function:
- Parse OpenAPI/Swagger JSON or YAML
- Extract schema definitions from components/schemas or definitions
- For each property in each schema, create a FieldInfo with:
  - source_name from the property key
  - inferred_type from the OpenAPI type field
  - description from the OpenAPI description field
  - format_pattern from the OpenAPI format field (date, date-time, int32, etc.)
- Return flat list of FieldInfo

After this step:
- git commit: feat(discovery): add JSON and OpenAPI parsers

### Step 3 Tests

JSON parser:
- Single JSON object produces FieldInfo for each key
- JSON array of objects produces FieldInfo with sample values from multiple records
- Nested objects produce FieldInfo with nesting_path (e.g. "address.city")
- Array of objects within a record produce FieldInfo with nesting_path (e.g. "exposures[].amount")
- Integer values inferred as "integer"
- Float values inferred as "decimal"
- Boolean values inferred as "boolean"
- Null values detected as nullable
- ISO date strings have format_pattern detected
- Mixed types in same field across records — inferred_type is "string" (safest)

OpenAPI parser:
- Simple schema with properties produces FieldInfo per property
- Description field from OpenAPI populates FieldInfo.description
- Format field from OpenAPI populates format_pattern
- Nested $ref schemas produce FieldInfo with nesting_path

### Step 3 Checklist
- [ ] src/discovery/parsers/json_parser.py exists
- [ ] parse_json handles single objects and arrays
- [ ] parse_json handles nested objects with dot-path notation
- [ ] parse_json detects date patterns in string values
- [ ] parse_openapi_spec extracts schema definitions
- [ ] All tests pass
- [ ] git commit done: feat(discovery): add JSON and OpenAPI parsers

---

## Step 4: XML Parser

Parse XML data (ACORD messages, SOAP responses) and extract field information.

What to create in src/discovery/parsers/xml_parser.py:

parse_xml(raw_input: str) -> list of FieldInfo function:
- Parse XML using lxml
- Detect namespaces — note ACORD namespace if present (commonly "http://www.ACORD.org/standards/PC_Surety/ACORD1/xml/")
- Walk the element tree
- For each element:
  - source_name is the tag name (strip namespace prefix for readability but store full qualified name in description)
  - Infer type from text content (try int, float, date patterns, boolean, fall back to string)
  - Collect sample values from text content
  - Handle attributes as separate FieldInfo entries with source_name like "element@attribute"
  - Build nesting_path from parent chain (e.g. "ClaimsSvcRq.ClaimsOccurrence.LossDt")
- Detect repeating elements (same tag name appears multiple times at same level) — these are arrays
- Return flat list of FieldInfo

detect_acord_version(raw_input: str) -> str or None function:
- Check for ACORD namespace in root element
- Check for Version attribute on root element
- Return version string if found, None if not ACORD

After this step:
- git commit: feat(discovery): add XML parser with ACORD detection

### Step 4 Tests

XML parser:
- Simple XML with text elements produces FieldInfo for each
- Nested XML produces FieldInfo with nesting_path
- XML attributes produce separate FieldInfo entries
- Namespace-prefixed elements have clean source_name (without prefix)
- Repeating elements detected (same tag multiple times)
- Date-like text content has format_pattern detected
- Empty elements produce FieldInfo with nullable=True

ACORD detection:
- ACORD XML with namespace returns version string
- Non-ACORD XML returns None
- ACORD XML without Version attribute returns "unknown"

### Step 4 Checklist
- [ ] src/discovery/parsers/xml_parser.py exists
- [ ] parse_xml handles namespaces, attributes, nesting
- [ ] ACORD namespace detected and noted
- [ ] Repeating elements identified as arrays
- [ ] detect_acord_version works
- [ ] All tests pass
- [ ] git commit done: feat(discovery): add XML parser with ACORD detection

---

## Step 5: CSV Parser

Parse CSV/TSV/pipe-delimited data and extract field information.

What to create in src/discovery/parsers/csv_parser.py:

parse_csv(raw_input: str) -> list of FieldInfo function:
- Use csv.Sniffer to detect delimiter (comma, pipe, tab, semicolon)
- Detect if first row is a header (Sniffer.has_header)
- If no header detected, generate synthetic headers (col_0, col_1, ...)
- Read all rows using detected dialect
- For each column:
  - source_name is the header value (cleaned: stripped whitespace, lowered for comparison but original case kept for source_name)
  - Sample up to 5 unique non-empty values
  - Infer type by trying conversions on sample values:
    - All values parse as int -> integer
    - All values parse as float -> decimal
    - All values match date patterns -> date or datetime
    - All values are "true"/"false"/"yes"/"no"/"1"/"0" -> boolean
    - Otherwise -> string
  - Detect format_pattern for dates: try YYYYMMDD, YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, MM-DD-YYYY, M/D/YYYY
  - Detect nullable (any empty cells in this column)
  - Detect currency patterns ($1,234.56 or 1234.56 or 1,234)
- Handle encoding issues: try utf-8, then latin-1, then cp1252
- Return list of FieldInfo

After this step:
- git commit: feat(discovery): add CSV parser with delimiter and type detection

### Step 5 Tests

- Comma-delimited CSV with headers parsed correctly
- Pipe-delimited file parsed correctly (delimiter detected)
- Tab-delimited file parsed correctly
- CSV without headers generates synthetic column names
- Integer column inferred as "integer"
- Decimal column inferred as "decimal"
- Date column (YYYY-MM-DD) inferred as "date" with format_pattern
- Date column (MM/DD/YYYY) detected with correct format_pattern
- Packed date (YYYYMMDD as integer like 20240115) detected with format_pattern
- Boolean column (true/false) inferred as "boolean"
- Column with mix of empty and filled values marked nullable
- Currency values ($1,234.56) detected with format_pattern

### Step 5 Checklist
- [ ] src/discovery/parsers/csv_parser.py exists
- [ ] Delimiter auto-detection works (comma, pipe, tab)
- [ ] Header detection works
- [ ] Type inference works for int, decimal, date, boolean, string
- [ ] Multiple date formats detected
- [ ] Nullable columns identified
- [ ] All tests pass
- [ ] git commit done: feat(discovery): add CSV parser with delimiter and type detection

---

## Step 6: Data Dictionary Parser

Parse human-written data dictionaries (markdown, text) to extract field definitions.

What to create in src/discovery/parsers/doc_parser.py:

parse_data_dictionary(raw_input: str) -> list of FieldInfo function:
- This handles markdown tables, plain text tables, and key-value listings that describe fields
- Detection patterns:
  - Markdown tables: lines with | separators and a --- header separator line
  - Tab-separated tables: lines with consistent tab-separated columns
  - Key-value: lines like "FIELD_NAME: description" or "FIELD_NAME - description"
- For each field found:
  - source_name from the field name column/key
  - description from the description column/value
  - inferred_type from type column if present, otherwise "unknown"
  - format_pattern from format column if present
- This parser is simpler than the data parsers — it gives us metadata, not sample values
- Return list of FieldInfo (many fields will have limited info — that's fine, the LLM analyzer fills gaps)

After this step:
- git commit: feat(discovery): add data dictionary parser

### Step 6 Tests

- Markdown table with columns (Field, Type, Description) parsed correctly
- Tab-separated table parsed correctly
- Key-value format (FIELD_NAME: description) parsed correctly
- Field names extracted accurately
- Descriptions populated in FieldInfo.description
- Type column mapped to inferred_type when present
- Empty/malformed input returns empty list (not an error — just no fields found)

### Step 6 Checklist
- [ ] src/discovery/parsers/doc_parser.py exists
- [ ] Handles markdown tables, tab tables, key-value formats
- [ ] Extracts field names, descriptions, types
- [ ] Gracefully handles malformed input
- [ ] All tests pass
- [ ] git commit done: feat(discovery): add data dictionary parser

---

## Step 7: LLM Analyzer

The intelligence layer — uses Claude to add insurance domain understanding to parsed fields.

What to create:

First, src/llm/__init__.py and src/llm/client.py:

LLMClient class:
- Takes anthropic API key from config
- async method: analyze(system_prompt: str, user_prompt: str, output_model: type[BaseModel]) -> BaseModel
- Sends request to Claude API (claude-sonnet-4-20250514)
- Parses response as JSON
- Validates against the provided Pydantic model
- If validation fails, retries once with error feedback appended to prompt
- If retry fails, raises LLMError
- Logs: prompt hash (not full prompt — privacy), token count, latency, success/failure
- Temperature 0.0 for all discovery/mapping calls

Then, src/discovery/analyzer.py:

InsuranceFieldAnalyzer class:
- Takes LLMClient as dependency
- async method: annotate_fields(fields: list of FieldInfo, source_format: str, notes: list of str) -> list of FieldInfo
- Sends the field list to Claude with a system prompt explaining:
  - You are an insurance data integration expert
  - You understand ACORD standards, Guidewire ClaimCenter, Duck Creek Claims, and legacy insurance systems
  - For each field, provide: insurance_annotation (what this field means in insurance terms), updated confidence score
  - If a field name is ambiguous, explain the ambiguity in the annotation
  - Common insurance synonyms you should know: excess=deductible, FNOL=first notice of loss, LOB=line of business, DOL/DT_OF_LSS=date of loss, CAT=catastrophe, SIU=special investigations unit, TPA=third party administrator, BI=bodily injury, PD=property damage, UM/UIM=uninsured/underinsured motorist, PIP=personal injury protection, subrogation=recovery rights
- Returns the annotated field list with insurance_annotation and confidence filled in
- Chunks the field list if more than 40 fields (MetaConfigurator research: LLM accuracy drops on large inputs)
- Processes chunks sequentially, not in parallel (rate limits)

After this step:
- git commit: feat(discovery): add LLM client and insurance field analyzer

### Step 7 Tests

LLMClient tests (mock the anthropic API — don't make real calls in tests):
- Successful API call returns validated Pydantic model
- API call with invalid response retries once
- API call that fails twice raises LLMError
- Logging captures latency and token count

InsuranceFieldAnalyzer tests (mock LLMClient):
- Fields with clear insurance names get annotations (e.g. "lossDate" -> "date of loss")
- Fields list longer than 40 gets chunked
- Each chunk is processed separately
- Results from chunks are combined into single list
- Field count in output matches field count in input

### Step 7 Checklist
- [ ] src/llm/__init__.py exists
- [ ] src/llm/client.py has LLMClient with analyze method
- [ ] LLMClient retries once on validation failure
- [ ] LLMClient raises LLMError on double failure
- [ ] LLMClient logs latency and token count
- [ ] src/discovery/analyzer.py has InsuranceFieldAnalyzer
- [ ] Analyzer chunks large field lists
- [ ] Analyzer includes insurance synonym knowledge in prompt
- [ ] All tests pass (with mocked LLM)
- [ ] git commit done: feat(discovery): add LLM client and insurance field analyzer

---

## Step 8: Discovery Engine Orchestrator

Wire everything together — the main entry point that takes raw data and produces a ClientProfile.

What to create in src/discovery/engine.py:

DiscoveryEngine class:
- Takes LLMClient as dependency
- async method: discover(raw_input: str or bytes, client_name: str, data_dictionary: str or None = None) -> ClientProfile
- Flow:
  1. Detect encoding if bytes, decode to str
  2. Call detect_format to determine format
  3. Route to correct parser (json, xml, csv) based on format
  4. If data_dictionary provided, also parse it and merge field descriptions into parsed fields
  5. Call InsuranceFieldAnalyzer to add domain annotations
  6. Build and return ClientProfile with all fields, notes, warnings
- Error handling: wrap each step, catch specific errors, add context, re-raise as DiscoveryError
- Log each step with timing

After this step:
- git commit: feat(discovery): add DiscoveryEngine orchestrator
- git tag: git tag -a phase-2-complete -m "Phase 2: Discovery Engine"

### Step 8 Tests

Full integration tests (mock LLM only — all parsers run for real):
- JSON input produces valid ClientProfile with correct source_format
- XML input produces valid ClientProfile
- CSV input produces valid ClientProfile
- JSON with data dictionary merges descriptions into fields
- Unknown format raises DiscoveryError
- Empty input raises DiscoveryError
- ClientProfile total_fields_detected matches actual field count
- ClientProfile notes include format-specific observations

### Step 8 Checklist
- [ ] src/discovery/engine.py has DiscoveryEngine class
- [ ] discover() handles JSON, XML, CSV inputs
- [ ] discover() merges data dictionary info when provided
- [ ] discover() calls LLM analyzer for insurance annotations
- [ ] Error handling wraps each step with context
- [ ] Logging captures timing for each step
- [ ] All tests pass
- [ ] Full test suite passes: pytest tests/ -v — all green
- [ ] ruff check src/ passes
- [ ] git commit done: feat(discovery): add DiscoveryEngine orchestrator
- [ ] git tag done: phase-2-complete

---

## Test Rules for This Phase

- Mock LLM calls in all tests — never make real API calls in test suite
- Use pytest-asyncio for async test functions: mark with @pytest.mark.asyncio
- Create sample data fixtures in tests/conftest.py for each format:
  - sample_json_claims: a JSON string with 3 claims in Guidewire-style format
  - sample_xml_claims: an XML string with 2 claims in ACORD-style format
  - sample_csv_claims: a CSV string with 4 claims in legacy mainframe style
  - sample_data_dictionary: a markdown table describing 10 fields
- Each parser test uses the corresponding fixture
- Test file names match source: test_discovery.py for engine, test specific parsers in test files as needed
- Mock responses should return realistic insurance field annotations

---

## What NOT to Build in This Phase

- No mapping logic — that's Phase 3
- No code generation — that's Phase 4
- No API endpoints — those come later
- No sample data files in samples/ directory yet — that's Phase 5
- No monitoring — that's Phase 6
- No file upload handling — discovery takes raw strings, not file objects

---

## Cursor Prompt

> Read .cursorrules, PROJECT.md, and docs/PHASE_2_SPEC.md. Phase 1 is complete — all schema models, enums, validators, BaseAdapter, and exceptions exist. Do NOT start building yet. First, create a detailed implementation plan: list every file you will create, what each contains, the order, and dependencies. Wait for my approval.
