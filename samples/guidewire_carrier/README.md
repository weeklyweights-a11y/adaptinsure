# Beacon Mutual Insurance — Guidewire ClaimCenter

- **System:** Guidewire ClaimCenter 10.x
- **Format:** JSON (REST API responses)
- **Naming:** camelCase
- **Dates:** ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)
- **Currency:** Decimal numbers (no formatting)
- **Enums:** Typelist codes (e.g. `CT:collision`, `CT:theft`)

## Files

| File | Description |
|------|-------------|
| `sample_claims.json` | 15 claims with nested exposures, contacts, transactions |
| `api_spec.json` | Simplified OpenAPI 3.0 for discovery |

## Validation

```bash
python -c "import json; d=json.load(open('samples/guidewire_carrier/sample_claims.json')); assert len(d)==15"
```
