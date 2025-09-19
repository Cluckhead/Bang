### Synthetic Analytics Alignment Test

This document explains the purpose and usage of the automated alignment test that verifies core synthetic analytics produced by `analytics/synth_analytics_csv_processor.py` match those from `analytics/synth_spread_calculator.py`.

#### What this test validates
- **Z-Spread**: parity of `z_spread` outputs (decimal, displayed as bps in logs)
- **G-Spread**: parity of `g_spread` outputs (decimal)
- **Effective Duration**: parity of `effective_duration` (years)
- **Modified Duration**: parity of `modified_duration` (years), using the same compounding rules as the calculator

#### Files involved
- `tests/test_synth_alignment.py`: the pytest that performs the checks
- `tools/diagnose_zspread_diff.py`: shared helpers to construct inputs for each pipeline and compute metrics
- `analytics/synth_analytics_csv_processor.py`: CSV pipeline under test
- `analytics/synth_spread_calculator.py`: reference pipeline (source of truth)

#### How it works (high-level)
1. The test locates the latest date available in `Data/sec_Price.csv`.
2. It samples a small set of securities that have a price on that date.
3. For each security, it builds two independent sets of inputs:
   - The "SC" path (spread calculator): curves, cashflows, dirty price, and compounding exactly as used by `synth_spread_calculator.py`.
   - The "CSV" path (analytics CSV): the same inputs constructed by the updated CSV pipeline.
4. It computes Z, G, Effective Duration, and Modified Duration for both paths using the same SpreadOMatic functions.
5. It asserts the results match within very tight tolerances.

#### Tolerances
- Z-Spread and G-Spread: `1e-6` (in decimal), i.e., equivalently 0.00001 bps tolerance
- Effective Duration and Modified Duration: `1e-9` years

These values are intentionally tight to detect any divergence in inputs or formulas.

#### Data prerequisites
- `Data/sec_Price.csv`
- `Data/curves.csv`
- `Data/schedule.csv`
- `Data/reference.csv` (optional but recommended for coupon data)
- `Data/sec_accrued.csv` (optional; used when present)

The test automatically handles base-ISIN lookups (hyphen-suffix removal) and robust date parsing in line with the calculator.

#### Run the test (PowerShell)
```powershell
# From the project root
pytest -q tests\test_synth_alignment.py

# Or with the launcher
py -3 -m pytest -q tests\test_synth_alignment.py
```

Expected output:
```text
.
```

#### Interpreting failures
- A failure indicates a mismatch in either inputs (curves, cashflows, dirty price, compounding) or formulas.
- Use the diagnostic tool to print detailed diffs of inputs for specific ISINs and dates:
```powershell
python .\tools\diagnose_zspread_diff.py --data .\Data --limit 10
```
This prints per-ISIN comparisons for curves, cashflow vectors, compounding, dirty price, and the computed metrics.

#### Extending coverage
- Increase the sample size in `tests/test_synth_alignment.py` from 10 to more rows.
- Add parametrization over multiple latest dates if you maintain historical snapshots of `sec_Price.csv`.
- Include OAS/KRD checks once both pipelines rely on exactly the same implementations and inputs for those metrics.

#### Troubleshooting tips
- Check that all required CSVs exist and contain data for the latest date.
- Ensure currency and day-count conventions map identically. The CSV pipeline now:
  - Sorts curve points by numeric term-in-years
  - Builds payment schedules via `generate_payment_schedule`
  - Extracts cashflows using `extract_cashflows` with `get_supported_day_basis`
  - Uses the same compounding rules when deriving Modified Duration


