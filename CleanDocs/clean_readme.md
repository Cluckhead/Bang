## Bond Analytics Data Quality Toolkit

An automated suite of tools for validating, monitoring, and analyzing fixed‑income securities data.

---

### Documentation

- For a technical overview of the architecture and data flow, see our [Technical Overview for Agents & Developers](./clean_TECHNICAL_OVERVIEW.md).
- For a comprehensive user guide and configuration reference, see the [Complete User Documentation](./clean_encyclopedia.md).

---

### Getting Started

```powershell
# 1) Install dependencies (recommended: in a virtual environment)
pip install -r requirements.txt

# 2) Run the web application (opens http://localhost:5000)
python app.py
```

### Common Tasks

```powershell
# Run end‑to‑end data quality checks and update dashboard cache
python run_all_checks.py

# Populate attribution cache (optional, for large attribution files)
python populate_attribution_cache.py
```

### Key Features (at a glance)

- Data ingestion, preprocessing, and validation
- Security/fund analytics (YTM, Z/G‑Spreads, durations, convexity, KRDs)
- Automated exception ticketing and suppression
- Dashboard with KPIs and drill‑downs
- Config‑first design with YAML settings

---

### Document Structure

- `CleanDocs/clean_readme.md` (this file): quick intro and links
- `CleanDocs/clean_TECHNICAL_OVERVIEW.md`: architecture, data flow, core components
- `CleanDocs/clean_encyclopedia.md`: detailed guides, schemas, and full reference (with an appendix copy of legacy combined docs)

### Tests

```powershell
# Run focused harness
pytest -q tests/test_fixed_income_harness.py

# Run all tests
pytest -q
```


