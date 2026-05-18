# AdaptInsure

AI-powered insurance adapter platform: discover client claim data formats, map fields to a universal schema, generate typed Python adapters, validate with contract and round-trip tests, and monitor schema drift after deployment.

## Stack

Python 3.12 · Pydantic v2 · Gemini API · Jinja2 · pytest · FastAPI (planned)

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env     # set GEMINI_API_KEY
pytest tests/ -v
```

## Layout

- `src/schema/` — universal claims model
- `src/discovery/` — format detection and profiling
- `src/mapping/` — semantic field matching
- `src/generator/` — adapter code generation
- `src/testing/` — contract, round-trip, and edge-case harness
- `src/monitor/` — drift detection and fix approval workflow
- `samples/` — synthetic Guidewire, ACORD, and legacy insurers

## License

See repository owner for terms.
