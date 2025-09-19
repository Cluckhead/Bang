# Test Coverage Improvement Plan

## Goals

- Raise overall coverage from 34% to 60% in 3 phases without slowing the suite (>90% of tests <1s each).
- Stabilize and fix 3 failing tests before adding new coverage.
- Prioritize core logic (data layer, analytics, bond calculations) over views; add view smoke tests only where they protect core flows.

## Context Summary

- App scope: data ingestion, quality checks, security analytics, attribution, synthetic analytics, and a web bond calculator (see `CleanDocs/clean_encyclopedia.md`).
- Critical runtime pillars:
  1. Unified data layer via `SecurityDataProvider` powering analytics
  2. Synthetic analytics (spreads, durations, OAS) and CSV processors
  3. Quality checks: staleness, max/min thresholds, metrics and ticketing
  4. Bond calculation engine and API

## Current Failures (stabilize first)

- `tests/test_bond_calculation_excel.py::test_calculate_spreads_and_oas_invokes_spreadomatic` — AttributeError from `bond_calculation.analytics_enhanced` API mismatch.
  - Action: Align `analytics` and `analytics_enhanced` exported function names/signatures; add adapter if needed. Verify patched functions used by `bond_calculation_excel.calculate_spreads_durations_and_oas`.
- `tests/test_integration_unified_provider.py::test_unified_data_provider` — depends on real `Data/` files.
  - Action: Provide minimal synthetic CSV fixtures in tests to avoid reliance on repo-large data; parametrize path to `SecurityDataProvider`.
- `tests/test_synth_alignment.py::test_alignment_core_metrics` — returns None.
  - Action: Ensure alignment function returns expected dict/df; add explicit tests for non-None and key fields.

## Prioritized Coverage Roadmap

### Phase 0 — Fast wins and failing tests (Target +4–6% total)

- Fix above 3 tests.
- Add unit tests around core helpers with high call frequency.

### Phase 1 — Core data + analytics (Target +10–14% total)

1. `analytics/metric_calculator.py` (5% → 70%)
   - Unit tests for:
     - Empty and malformed inputs → empty df
     - MultiIndex requirements error path
     - Single-fund vs multi-fund metrics; correct latest date selection
     - Z-score edges: NaN/inf/zero-std handling
     - Relative metrics merge and sorting by max|Z|
2. `analytics/staleness_processing.py` (41% → 75%)
   - Detect staleness with placeholders, configurable thresholds, edge windows.
3. `analytics/maxmin_processing.py` (56% → 80%)
   - Threshold breaches, inclusivity, per-file configs.
4. `analytics/issue_processing.py` (34% → 70%) & `analytics/ticket_processing.py` (47% → 70%)
   - Ticket creation from anomalies; idempotency; merging; CSV write guarded by io_lock mock.
5. `core/utils.py` (38% → 85%)
   - Date column detection, safe reads/writes, yaml loader fallbacks, type coercions.
6. `core/data_loader.py` (52% → 75%) and `core/settings_loader.py` (49% → 80%)
   - Settings cache invalidation, secondary file fallback (`config/…yaml`), settlement conventions selection.

### Phase 2 — Bond calculations + unified data (Target +8–12% total)

7. `analytics/security_data_provider.py` (82% → 92% with critical invariants)
   - ISIN normalization/suffix rules, currency precedence, accrued interest priority (exact/prev/base schedule), curve filtering by date/currency, Excel-serial date parsing.
8. `bond_calculation/analytics.py` & `analytics_enhanced.py` (9–13% → 70%)
   - Deterministic tests for:
     - YTM monotonicity (price↓ → yield↑)
     - Z- and G-spread sign conventions and invariants
     - Effective vs modified duration relationship
     - Convexity positivity on plain bonds
     - Key-rate durations sum bounds
     - OAS: enhanced/standard selection guard and graceful fallback
9. `bond_calculation/bond_calculation_excel.py` (28% → 60%)
   - Unit-test pure builders (cashflows, curve prep, mapping); simulate Excel writer via NamedTemporaryFile; assert worksheet presence/headers (existing smoke extended).
10. `analytics/synth_spread_calculator.py` (11% → 45%) and `analytics/synth_analytics_csv_processor.py` (10% → 40%)
    - Mini end-to-end with tiny CSV fixtures (2 securities × 2 dates) asserting non-null output coverage and expected columns per file; avoid performance-heavy paths via monkeypatch.

### Phase 3 — Data preprocessing + API/views smoke (Target +6–10% total)

11. `data_processing/preprocessing.py` (6% → 40%)
    - `read_and_sort_dates` error branches; `replace_headers_with_dates` regex mapping; `aggregate_data` duplicate handling with `suffix_isin`; long→wide pivot path with ref enrichment.
12. `data_processing/data_audit.py` (50% → 70%) and `data_validation.py` (55% → 75%)
    - Cross-file consistency minimal fixtures (e.g., missing schedule row), explicit failure messages.
13. API/view smoke tests (each 1–3 assertions; fast):
    - `views/synth_analytics_api.py` POST happy-path with mini fixtures
    - A few GET endpoints return 200 and contain expected keys: `/`, `/security/summary`, `/bond/api/calc`
    - Use Flask test client; feature-flag heavy dependencies off.

### Phase 4 — Real code execution + SpreadOMatic integration (Target +8–15% total)

14. Real execution tests (reduce mocking, test actual business logic):
    - `core/utils.py` (85% → 95%) - Execute actual date parsing, fund list processing, YAML loading without mocks
    - `analytics/security_data_provider.py` (92% → 98%) - Real CSV loading, ISIN normalization, currency precedence logic
    - `analytics/metric_calculator.py` (70% → 85%) - Actual statistical calculations, Z-score computation, MultiIndex operations
    - `data_processing/data_validation.py` (75% → 90%) - Real validation rules execution, pandas operations
15. SpreadOMatic integration tests (conditional on availability):
    - `tools/SpreadOMatic/spreadomatic/yield_spread.py` - Real YTM solving with synthetic bonds
    - `tools/SpreadOMatic/spreadomatic/duration.py` - Actual duration calculations with bump-and-reprice
    - `tools/SpreadOMatic/spreadomatic/discount.py` - Real discount factor calculations
    - Basic OAS calculation with simple callable bond (avoid Monte Carlo for speed)
16. End-to-end integration tests with real data flow:
    - `analytics/synth_spread_calculator.py` (45% → 65%) - Real calculation pipeline with mini CSV fixtures
    - `bond_calculation/analytics.py` (70% → 85%) - Actual bond math with SpreadOMatic functions
    - Cross-module integration: SecurityDataProvider → Bond Analytics → Synthetic Output

## Test Suite Structure

- `tests/unit/…`
  - `core/test_utils_datetime.py`, `core/test_settings_loader.py`
  - `analytics/test_metric_calculator.py`, `test_staleness_processing.py`, `test_issue_ticket_processing.py`
  - `bond_calculation/test_analytics_invariants.py`, `test_daycount_precision.py`, `test_cashflows.py`
  - `analytics/test_security_data_provider.py`
- `tests/integration/…`
  - `test_synth_spreads_minimal.py` (tiny CSV flow)
  - `test_bond_calc_api.py` (Flask client)
  - `test_provider_roundtrip.py` (provider→calc invariants)
- `tests/data/mini/`
  - `reference.csv`, `schedule.csv`, `sec_Price.csv`, `sec_accrued.csv`, `curves.csv` (2 ISINs × 2 dates, tiny)

## Key Test Design Details (by module)

- `analytics/metric_calculator.py`
  - Build small MultiIndex dfs with primary/secondary, include NaNs; assert z-score calculations (NaN, ±inf for zero-std), sorting key `_sort_z` workflow via public output order.
- `analytics/security_data_provider.py`
  - Parametrize ISIN forms (dashes/unicode), dates (ISO, dd/mm/yyyy, Excel serial), and fallback priority for accrued.
  - Verify currency choice order: Position Currency > Currency > Price Currency > default.
- `bond_calculation` (analytics & enhanced)
  - Synthetic cashflows for fixed-rate bullet; assert:
    - Price(y) strictly decreasing; duration positive; convexity ≥ 0
    - Modified duration ≈ eff/(1+y/m) relation within tolerance
    - z_spread(+) increases price discount; g_spread consistent given curve
- `data_processing/preprocessing.py`
  - `replace_headers_with_dates`: columns [Field, Field.1, Field.2] → supplied dates; partial replacement on length mismatch; no-op when no pattern.
  - `aggregate_data`: duplicates by security name create suffixed ISIN using `config.ISIN_SUFFIX_PATTERN`.
- issue/ticket processing
  - Feed anomalies and assert stable ticket IDs, dedupe/idempotency when re-run, CSV write mocked.

## Fixtures, Fakes, and Helpers

- Mini CSV fixtures in `tests/data/mini/` created on-the-fly using `tmp_path`.
- Monkeypatch `core.config.DATA_FOLDER` and any module-level path accessors to point at mini dataset.
- Mock heavy functions: Monte Carlo OAS, Excel writers; gate via `ENHANCED_OAS_AVAILABLE` and function monkeypatches.
- Freeze time for date-sensitive logic (freezegun).
- Hypothesis where valuable:
  - ISIN normalizer (strings with hyphen/dashes) → normalized invariants
  - Date parsers round-trip and equality across formats
  - Price/yield monotonicity for a range of coupons/prices

## Performance and Stability

- Keep per-test runtime <50ms when possible; mark slow/long-running tests with `@pytest.mark.slow` and run in nightly job only.
- Make integration tests deterministic by seeding RNG and patching any non-deterministic sources.

## CI and Coverage Policies

- Switch CI to pytest + coverage:
  - `pytest -q --maxfail=1 --disable-warnings --cov --cov-report=term-missing`
  - Gate on incremental threshold: start with `--cov-fail-under=40`, raise by 5pp after each phase to 60.
- Keep `.coveragerc` simple; consider excluding generated Excel sheet modules if they inflate lines with little risk.

## Milestones & Targets

- Phase 0 (day 0–1): Fix failing tests; add 6–8 unit tests for utils/provider; target 38–40%.
- Phase 1 (days 2–4): Metric + staleness + max/min + ticketing; target 50–54%.
- Phase 2 (days 5–7): Bond calc invariants + provider edge cases; target 58–62%.
- Phase 3 (days 8–9): Preprocessing + API smoke + audits; target 60–65%.
- Phase 4 (days 10–12): Real code execution + SpreadOMatic integration; target 68–80%.

## Risks & Mitigations

- Heavy I/O dependence: Use tmp_path + in-memory fixtures; monkeypatch file paths.
- Flakiness from real data: Eliminate reliance on repo `Data/`; ship tiny synthetic fixtures.
- Enhanced analytics variability: Gate behind feature flags and patch heavy paths for unit tests; keep true-accuracy checks in nightly.

## Acceptance Criteria

- Total coverage ≥ 60% (Phase 4 stretch goal: ≥ 75%), with the following file targets hit:
  - `core/utils.py` ≥ 80% (Phase 4: ≥ 95%)
  - `analytics/metric_calculator.py` ≥ 70% (Phase 4: ≥ 85%)
  - `analytics/security_data_provider.py` ≥ 90% (Phase 4: ≥ 98%)
  - `bond_calculation/analytics.py` & `analytics_enhanced.py` ≥ 70% (Phase 4: ≥ 85%)
  - `data_processing/preprocessing.py` ≥ 40%
  - `data_processing/data_validation.py` ≥ 75% (Phase 4: ≥ 90%)
  - SpreadOMatic core modules ≥ 60% (Phase 4 only, conditional on availability)
- All tests pass locally; CI runs pytest with coverage gate; no reliance on large `Data/` folder for core suite.
- Phase 4: Actual code execution measured (not just mocked), with real SpreadOMatic calculations tested.

---

## Detailed Test Cases (Actionable)

This section expands each target with concrete test cases, fixtures, and how to accomplish them. Use pytest with tmp_path, monkeypatch, and Flask’s test client. Prefer parametrization to keep tests small and fast.

### Global Test Harness

- Fixture: mini_dataset(tmp_path)
  - Creates minimal CSVs under `tmp_path`: `reference.csv`, `schedule.csv`, `sec_Price.csv`, `sec_accrued.csv`, `curves.csv`, `w_secs.csv`, `FundGroups.csv`, `holidays.csv`.
  - Returns the folder path for use by modules that read from disk.
- Fixture: app_config(monkeypatch, tmp_path)
  - monkeypatch `core.settings_loader.load_settings` to return `{ 'app_config': { 'data_folder': str(tmp_path) } }`.
  - Ensures functions using `get_app_config()` resolve to the temporary dataset.
- Fixture: freeze_time
  - Use `freezegun.freeze_time("2025-01-03 10:00:00")` for tests that rely on “today/last business day”.
- Helper: write_csv(path, rows)
  - Utility to quickly materialize small CSVs from lists of dicts.

Minimal dataset shape and example rows (produce only the columns referenced by tests):

```
reference.csv
ISIN,Security Name,Position Currency,Currency,Coupon Rate,Call Indicator,Funds,Type,Is Distressed
US0000001,Bond A,EUR,USD,5.0,1,[F1],Corp,False
US0000002,Bond B,GBP,USD,3.0,0,[F2],Gov,True

schedule.csv
ISIN,Coupon Frequency,Day Basis,Issue Date,First Coupon,Maturity Date,Accrued Interest
US0000001,2,ACT/ACT,01/01/2020,01/07/2020,01/01/2030,1.23
US0000002,2,30/360,01/01/2021,01/07/2021,01/01/2031,0.45

sec_Price.csv
ISIN,Security Name,Type,Funds,Callable,Currency,2025-01-01,2025-01-02
US0000001,Bond A,Corp,[F1],Y,USD,100.1,101.2
US0000002-1,Bond B (tap),Gov,[F2],N,USD,99.8,99.5

sec_accrued.csv
ISIN,2025-01-01,2025-01-02
US0000001,1.11,1.22  
US0000002,0.33,

curves.csv
Currency Code,Date,Term,Daily Value
USD,2025-01-02,1M,5.0
USD,2025-01-02,1Y,5.5
USD,2025-01-02,5Y,6.0
EUR,2025-01-02,1Y,3.0

w_secs.csv
ISIN,2024-01-01,2025-01-02
US0000001,0,0.15
US0000002,0.10,0

FundGroups.csv
Group,Funds
Core,[F1,F2]

holidays.csv
date,currency
2025-01-01,GBP
```

### Phase 0 – Current Failures

1) tests/test_bond_calculation_excel.py::test_calculate_spreads_and_oas_invokes_spreadomatic
   - Purpose: Verify `bond_calculation.bond_calculation_excel.calculate_spreads_durations_and_oas` delegates to enhanced then standard functions without AttributeError.
   - How: monkeypatch `bond_calculation.analytics_enhanced.calculate_spreads_durations_and_oas` to return a dict; assert values flow through. Add a second test that raises ImportError and asserts fallback to `bond_calculation.analytics.calculate_spreads_durations_and_oas`.

2) tests/test_integration_unified_provider.py::test_unified_data_provider
   - Purpose: Remove reliance on repo `Data/` by using `mini_dataset`.
   - How: Instantiate `SecurityDataProvider(str(tmp_path))`; call `get_security_data('US0000001','2025-01-02')`; assert fields merged (price>0, coupon_rate=5.0, maturity_date parsed, currency=Position Currency precedence).

3) tests/test_synth_alignment.py::test_alignment_core_metrics
   - Purpose: Ensure alignment helper returns non-None with expected keys.
   - How: Target public function under test; monkeypatch heavy subcalls to return minimal dicts; assert type and keys.

### analytics/metric_calculator.py

- test_metric_empty_df_returns_empty
  - Given empty df → `calculate_latest_metrics` returns empty df with columns.
- test_metric_requires_multiindex
  - Given df without MultiIndex [Date, Fund Code] → raises/handles error path (assert log/empty output depending on API).
- test_metric_single_fund_latest_date_selection
  - Given two dates; as-of chosen correctly; latest metrics use last date.
- test_metric_change_zscore_nan_inputs
  - Ensure Z-score is NaN when inputs NaN; test inf when std==0 and latest_change != mean.
- test_metric_relative_merge_and_sort
  - Provide primary and secondary inputs; assert relative metrics appear and `_max_abs_z` sorting influences order.

Data setup: Build small MultiIndex df with index=(Date, Fund Code) and columns `['Fund', 'Bench']` or appropriate names expected by the module; include NaNs to exercise branches.

### analytics/staleness_processing.py

- test_stale_last_n_identical_non_zero_numeric
  - Last N non-null values equal and non-zero → flagged stale; include `threshold_days=3`.
- test_zero_sequences_not_stale
  - Last N values equal to 0 → not stale.
- test_non_numeric_repeating_values_stale
  - Repeating non-numeric (e.g., 'N/A') across last N → not counted as stale; only non-null values are considered.
- test_skips_excluded_ids
  - Provide exclusions_df with matching id; ensure it’s skipped.
- test_latest_date_parsing_and_summary_counts
  - Verify `latest_date` string set; `stale_percentage` correct.

How: Write a tiny `sec_*.csv` with 1–2 rows and 4 date columns; call `get_stale_securities_details` and `get_staleness_summary`.

### analytics/maxmin_processing.py

- test_breaches_above_and_below_thresholds
  - Values > max or < min are collected with correct metadata.
- test_skip_distressed_by_default
  - `reference.csv` with Is Distressed TRUE → excluded unless `include_distressed=True`.
- test_get_breach_summary_uses_overrides
  - Pass overrides; ensure reported `max_threshold`/`min_threshold` reflect overrides; counts match.
- test_get_breach_details_aggregates_per_security
  - Multiple date breaches aggregated into one entry with `count`, `dates`, `values`.

How: Use `mini_dataset` and write a small `sec_*.csv` specific to the test.

### analytics/issue_processing.py

- test_load_issues_adds_missing_columns_and_types
  - Start with CSV missing some REQUIRED_ISSUE_COLUMNS; ensure loader adds with defaults and persists.
- test_add_issue_creates_incrementing_issue_id
  - Call twice; expect `ISSUE-001`, then `ISSUE-002`.
- test_close_issue_idempotency
  - Close once → True; second close → False; fields set (DateClosed, ClosedBy, ResolutionComment).
- test_load_fund_list_finds_column_variants
  - Supports `FundCode`, `Code`, `Fund Code`; returns sorted unique list.
- test_comments_serialize_roundtrip
  - `add_comment_to_issue` appends JSON; deserialize and verify content.

How: Use tmp CSVs; ensure `_save_issues` writes back; read again to verify.

### analytics/security_data_provider.py

- test_normalize_isin_handles_unicode_dashes_and_case
  - Input `'us0000001\u2013a'` → `'US0000001-A'`.
- test_get_base_isin_removes_suffix
  - `'US0000002-1'` → `'US0000002'`.
- test_currency_precedence_reference_over_price
  - With `reference.csv` Position Currency=EUR and price Currency=USD → returns EUR.
- test_accrued_interest_exact_date
  - Exact ISIN/date in `sec_accrued.csv` returns value.
- test_accrued_interest_previous_date
  - No exact match; pick nearest previous date column.
- test_accrued_interest_base_isin_fallback
  - ISIN with suffix uses base row if present.
- test_accrued_interest_schedule_fallback
  - No accrued row; falls back to `schedule.csv` Accrued Interest; else 0.0.
- test_get_schedule_and_reference_fallback_to_base
  - Suffix ISIN returns base row when exact not present.
- test_get_curves_data_filters_by_currency_and_date
  - Filters on currency and date prefix (YYYY-MM-DD), returns non-empty df.
- test_get_security_data_merges_all
  - Returns `SecurityData` with merged fields (callable, coupon_rate, currency, dates, accrued); non-null sanity checks.

How: Instantiate provider with `mini_dataset` path; verify methods above.

### bond_calculation/analytics.py

- test_monotonic_ytm_vs_price
  - Lower price → higher ytm. Build simple cashflows and zero curve; call twice with two prices.
- test_duration_relationship
  - `modified_duration` ≈ `effective_duration / (1 + ytm/freq)` within tolerance (e.g., 1e-2).
- test_convexity_positive_plain_bond
  - `convexity > 0` for fixed-rate bullet.
- test_spreads_signs
  - Reasonable curve and price below par → z_spread > 0; g_spread has expected sign.
- test_key_rate_durations_presence
  - Returns KRDs dict/list with > 0 entries; sum is within plausible bounds of effective duration.
- test_oas_graceful_when_no_calls
  - No call_schedule in bond_data → OAS fields are None; no exception.

How: Synthesize 10Y semi-annual cashflows at 5% coupon, price near par, simple upward sloping zero curve.

### bond_calculation/analytics_enhanced.py

- test_enhanced_fallback_path
  - If enhanced modules missing, `calculate_spreads_durations_and_oas_enhanced` returns result from fallback path with `'calculated': True` and keys present.
- test_enhanced_g_spread_consistency
  - Regardless of enhanced availability, g_spread computation remains consistent for given ytm/maturity/curve.

How: monkeypatch imports or guard flags to exercise both enhanced and fallback branches.

### bond_calculation/bond_calculation_excel.py

- test_generate_cashflows_and_prepare_payment_schedule
  - Ensure functions return non-empty structures compatible with workbook builder.
- test_write_enhanced_excel_smoke
  - Monkeypatch `build_workbook` to return a real Workbook; call `write_enhanced_excel_with_oas` with tmp output path; assert file exists and is a valid XLSX (openpyxl load).
- test_calculate_spreads_bridge_to_enhanced_then_standard
  - Monkeypatch enhanced to raise ImportError; ensure standard analytics used; result keys present.

### analytics/synth_spread_calculator.py

- test_convert_term_to_years_parsing
  - '7D'→~0.019, '1M'→~0.0833, '2Y'→2.0; invalid raises ValueError.
- test_build_zero_curve_exact_date
  - For USD 2025-01-02; returns times/rates sorted; `is_fallback=False`.
- test_build_zero_curve_fallback_previous_date
  - If missing on target date, picks nearest previous date and returns `is_fallback=True` with warning.
- integration-lite: test_provider_to_synth_timeseries
  - Use `SecurityDataProvider` + `build_zero_curve` to feed a calculator helper that requires only curve and cashflows; assert that output numeric fields are finite.

### data_processing/preprocessing.py

- test_read_and_sort_dates_nominal
  - Mixed formats and duplicates → unique YYYY-MM-DD sorted list.
- test_read_and_sort_dates_errors
  - Missing file; non-date rows; non-datetime convertible path → returns None with log.
- test_replace_headers_with_dates_exact_count
  - Columns `Field, Field.1, Field.2` replaced by the first N dates; non-matching columns untouched.
- test_replace_headers_with_dates_length_mismatch
  - More columns than dates → only min(count) replaced; warning emitted.
- test_replace_headers_with_dates_no_pattern_noop
  - No `<prefix>.<n>` headers → df unchanged.
- test_suffix_isin_pattern
  - Uses `config.ISIN_SUFFIX_PATTERN` to suffix duplicates deterministically.
- test_aggregate_data_group_and_suffix
  - For duplicate securities across id_cols → `Funds` merged `[...]` and ISIN suffixed; column set preserved.
- test_process_input_file_long_format_pivot
  - Provide long-format csv with `Date, Value`; pivot to wide; handles accrued weight special-casing; writes output.

### data_processing/data_audit.py

- test_audit_collects_date_ranges_and_structure
  - On `mini_dataset`, `run_data_consistency_audit` returns summary with `all_match` computed and file_details populated.
- test_audit_marks_blank_columns_and_only_header
  - Create a csv with blank column header and no rows; expect structure issues and recommendations populated.
- test_audit_ts_and_sec_fund_presence
  - For ts_/sp_ts_ sample files, ensure fund presence issues reported when funds missing by date.

### data_processing/data_validation.py

- test_validate_ts_happy_path
  - Valid df with Date/Code numeric values → (True, []).
- test_validate_ts_missing_required
  - Missing Code → (False, [error msg]).
- test_validate_ts_non_numeric_values
  - Non-numeric value columns → (False, contains 'not numeric').
- test_validate_sec_date_like_columns
  - Wide file with date-like columns non-numeric or unparseable → errors returned; with numeric values → no errors.
- test_validate_weights_header_dates
  - Weight file: first column id; subsequent columns valid dates and numeric → passes; invalid date headers → errors.

### core/utils.py

- test_is_date_like_patterns
  - True for '2025-01-01', '01/01/2025', 'Date'; False for 'foo'.
- test_load_yaml_config_missing_and_parse_error
  - Missing file → {}; malformed yaml temp file → {}.
- test_parse_fund_list_variants
  - '[]'→[]; '[A,B]'→['A','B']; 'A, B'→['A','B']; None→[].
- test_get_data_folder_path_from_settings_absolute_and_relative
  - monkeypatch settings to `{data_folder: 'Data'}` and config.BASE_DIR to tmp; create folder; expect resolved absolute path. Missing folder → FileNotFoundError.
- test_load_exclusions_parses_dates
  - Writes AddDate/EndDate columns; returns df with datetime dtypes; missing file → None.
- test_load_weights_and_held_status_latest_value_gt_zero
  - `w_secs.csv` latest date weight > 0 → True; zeros/NaN → False; handles id_col_override fallback.
- test_replace_nan_with_none_recursive
  - Nested dict/list with np.nan → None in all numeric-NaN positions; other values preserved.
- test_load_fund_groups_parses_and_maps
  - Map group → funds list via parse_fund_list; missing file → {}.
- test_check_holidays_and_filter_business_dates
  - With `holidays.csv` and freeze_time to 2025-01-03 (Fri): detect holiday on last business day for GBP; filter excludes weekend/holiday.
- test_get_business_day_offset_skips_weekends
  - From Friday with offset +1 returns Monday; -1 returns Thursday.

### core/data_utils.py

- test_read_csv_robustly_error_paths
  - FileNotFound → None; EmptyDataError → None; ParserError path via malformed csv → None.
- test_parse_dates_robustly_various_formats
  - ISO, DD/MM/YYYY, Excel serial (e.g., 45567) → datetime; invalid → NaT.
- test_identify_columns_found_and_missing
  - Patterns locate id/date; missing required raises ValueError with readable message.
- test_replace_zeros_with_nan_numeric_only
  - Numeric series zeros→NaN; non-numeric unchanged.
- test_convert_to_numeric_robustly_and_zero_replace
  - Coerce invalid to NaN; zeros replaced when `replace_zeros=True`.
- test_melt_wide_data_date_detection_and_parsing
  - Wide df with date-like columns → returns long df with parsed Date; no date-like columns → None.

### views/synth_analytics_api.py (smoke)

- test_get_info_returns_expected_keys
  - Flask test client; monkeypatch app config DATA_FOLDER to `mini_dataset`; assert JSON keys: `latest_date`, `securities_count`, `available_analytics`, `enhanced_analytics_available`.
- test_generate_job_lifecycle
  - POST /generate → status started + job_id; GET /job_status/<id> returns queued/running; monkeypatch `generate_comprehensive_analytics_csv` to fast-complete and set output_path; then GET /download/<id> returns file; error branches for invalid id/status.
- test_list_and_download_files_security
  - Write a valid `comprehensive_analytics_*.csv` in data folder; GET /list_files returns it; /download_file/<filename> works; invalid filename rejected with 400.

### Phase 4 — Real Code Execution (Detailed)

#### Real Execution Strategy (No Mocking)

**Objective**: Test actual business logic execution to achieve meaningful coverage metrics, not just test structure validation.

#### core/utils.py (Real Execution Tests)

- test_parse_fund_list_real_execution
  - Execute actual string parsing logic with various formats: `'[F1,F2]'`, `'F1, F2, F3'`, `''`, `None`; assert exact parsed results.
- test_is_date_like_real_pattern_matching
  - Execute actual regex pattern matching with DATE_COLUMN_PATTERNS; test with 20+ real column names from production data.
- test_load_yaml_config_real_file_operations
  - Create real YAML files with valid/invalid content; execute actual file I/O and YAML parsing; assert parsed structure.
- test_get_business_day_offset_real_datetime_arithmetic
  - Execute actual datetime calculations with real pandas business day logic; test weekends, holidays, edge cases.
- test_replace_nan_with_none_real_recursive_traversal
  - Execute actual recursive traversal with deeply nested structures containing numpy NaN values.

#### analytics/security_data_provider.py (Real Data Operations)

- test_real_csv_loading_and_merging
  - Use real pandas read_csv operations on mini_dataset; test actual DataFrame merging, ISIN matching, currency precedence.
- test_real_isin_normalization_string_operations
  - Execute actual string operations: `.upper()`, `.replace()`, unicode character handling; test with 50+ ISIN variants.
- test_real_accrued_interest_fallback_chain
  - Execute actual pandas DataFrame lookups across multiple files; test exact date → previous date → base ISIN → schedule fallback.
- test_real_cache_invalidation_file_mtime
  - Execute actual file system mtime checking; modify real files and verify cache invalidation triggers.

#### analytics/metric_calculator.py (Real Statistical Calculations)

- test_real_multiindex_dataframe_operations
  - Execute actual pandas MultiIndex operations: `.loc[]`, `.groupby()`, `.agg()`; test with real time-series data.
- test_real_zscore_statistical_calculations
  - Execute actual numpy statistical functions: `.mean()`, `.std()`, z-score formula; test with real distributions including edge cases.
- test_real_dataframe_sorting_and_merging
  - Execute actual pandas sorting by `_sort_z` column; test DataFrame merging with outer joins.

#### SpreadOMatic Integration Tests (Conditional)

**Note**: Only run if SpreadOMatic modules are available; mark with `@pytest.mark.skipif` otherwise.

#### tools/SpreadOMatic/spreadomatic/yield_spread.py

- test_real_ytm_solving_newton_raphson
  - Execute actual Newton-Raphson iteration with real cashflows; synthetic 5Y bond at 95, 100, 105 prices; assert YTM convergence.
- test_real_z_spread_curve_interpolation
  - Execute actual linear interpolation and spread solving; test with real zero curve; assert spread values reasonable.
- test_real_g_spread_government_interpolation
  - Execute actual government curve interpolation at maturity; test with real curve data.

#### tools/SpreadOMatic/spreadomatic/duration.py

- test_real_effective_duration_bump_reprice
  - Execute actual bump-and-reprice: price bond at yield±1bp; calculate (PV_down - PV_up)/(2 × PV_base × 0.0001).
- test_real_modified_duration_macaulay_calculation
  - Execute actual Macaulay duration calculation from cashflow PV weights; apply frequency adjustment.
- test_real_convexity_second_derivative
  - Execute actual second derivative calculation: (PV_up + PV_down - 2×PV_base) / (PV_base × bump²).

#### tools/SpreadOMatic/spreadomatic/discount.py

- test_real_discount_factor_compounding
  - Execute actual compounding calculations: annual, semiannual, quarterly, continuous; test with various rates and times.
- test_real_pv_cashflows_summation
  - Execute actual present value calculations: sum(cashflow × discount_factor); test with real bond cashflows.

#### Integration Tests (Real End-to-End)

#### analytics/synth_spread_calculator.py (Real Pipeline)

- test_real_security_data_to_spread_calculation
  - Execute actual SecurityDataProvider → spread calculation pipeline; mini_dataset with 2 bonds; assert real YTM/spread values.
- test_real_csv_output_generation
  - Execute actual CSV writing with real pandas to_csv; verify output file structure and content.

#### bond_calculation/analytics.py (Real Bond Math)

- test_real_bond_analytics_full_calculation
  - Execute actual SpreadOMatic functions with real bond data; synthetic 10Y bond; assert all analytics (YTM, spreads, duration, convexity).
- test_real_oas_calculation_simple_callable
  - Execute actual OAS calculation with simple call option; avoid Monte Carlo (use binomial tree with 10 steps max).

#### Cross-Module Integration

- test_real_provider_to_bond_calculation_roundtrip
  - SecurityDataProvider → bond_calculation/analytics → verify mathematical consistency; test with 3 different bond types.
- test_real_synthetic_analytics_end_to_end
  - Real data flow: mini_dataset → SecurityDataProvider → synth_spread_calculator → CSV output; verify complete pipeline.

---

## How We'll Implement (Step-by-Step)

**Phases 0-3 (Completed)**:
- Create `tests/conftest.py` with fixtures: `mini_dataset`, `app_config`, `client` (Flask), and helpers for writing CSVs.
- Build module-focused test files as listed in "Test Suite Structure", using the named tests above.
- Use pytest markers for `slow` where needed; default everything else fast and deterministic (seed RNG, patch env).
- Keep expectations numeric-light: assert types, monotonicity, presence, and tolerances rather than exact values for SpreadOMatic paths.
- For heavy/external deps, prefer monkeypatching or feature flags (e.g., ENHANCED_* guards) to keep runtime small and reliable.

**Phase 4 (Real Execution)**:
- Create `tests/real_execution/` directory for unmocked tests that execute actual business logic.
- Build tests that import and execute actual functions without mocking core business logic.
- Use conditional imports with `@pytest.mark.skipif` for SpreadOMatic dependencies.
- Test real file operations using `tmp_path` but with actual pandas/numpy operations.
- Validate actual mathematical calculations with known inputs/outputs.
- Measure real code coverage to achieve meaningful coverage metrics (target 75%+).

## Execution Commands

**Phases 0-3 (Mocked Tests)**:
- Run core fast subset: `pytest tests/unit/core -q`
- Run all unit tests with coverage: `pytest -q --maxfail=1 --disable-warnings --cov --cov-report=term-missing`
- Integration-only (local smoke): `pytest tests/integration -q`

**Phase 4 (Real Execution Tests)**:
- Run real execution tests: `pytest tests/real_execution/ --cov=analytics,core,data_processing --cov-report=term-missing`
- Run SpreadOMatic tests (conditional): `pytest tests/real_execution/test_spreadomatic_*.py -v`
- Run full coverage with real execution: `pytest tests/real_execution/ tests/test_core_utils_phase0.py tests/test_security_data_provider_phase0.py --cov=. --cov-report=html`
- Measure actual coverage: `coverage run --source=analytics,core,data_processing -m pytest tests/real_execution/ && coverage report --show-missing`
