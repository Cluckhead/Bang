# Project Plan – "WhoNeedsSP"

A practical, incremental roadmap for **removing dependency on third-party vendor analytics (e.g. S&P)** and replacing them with fully-transparent, in-house calculations.

> Universe constraints
> • Only cash bonds (no securitisations, no derivatives).  
> • Most complex structure is **fixed-to-variable**.  
> • **Curves already exist** in `Data/curves.csv` and cover every `Date × Currency`.  
> • **Clean price** is already loaded – *Original* and *S&P* layers point to **the same price source**, so only ***one*** price file is required.
> • **Perpetuals are common.**  We assume the first call date (if any) acts as a *pseudo-maturity*; if no call exists the horizon is capped at 100 years for PV maths.

All analytics will therefore exist in three parallel flavours:

| Layer | Source | Notes |
|-------|--------|-------|
| **Original**  | Raw vendor files already loaded | Baseline used today |
| **S&P Overlay** | Vendor-calculated analytics | Used for comparison but shares the same price feed |
| **Calculated** | New internal engine | Implemented by this plan |

---

## Why Bother?  –  Data-Validation Benefits

1. **Ground-Truth Check** – Calculated values provide an independent benchmark; any large gap to *Original* or *S&P* is a red flag.
2. **Auditability** – Hand-rolled maths ⇒ no black-box vendor, every assumption lives in code & CSV.
3. **Deterministic Re-runs** – Calculations can be replayed off-line for any historical date without licensed tools.
4. **Faster Root-Cause Analysis** – When spreads look wrong you can drill into price/yield reconciliation directly in the app.

---

## Data Requirements

### Existing Inputs (no change)
* `Data/curves.csv` – risk-free zero/par curves.
* `sec_Price.csv` – daily **clean** prices. (Shared by all layers.)
* `reference.csv` – static metadata (ISIN, Name, Currency, etc.).

### New / Extended Inputs

| File | Purpose | Key Columns |
|------|---------|------------|
| `reference.csv` (extend) | Coupon & schedule | `CouponRate, CouponFrequency, DayCount, IssueDate, MaturityDate, FaceValue, FirstFixToVarDate` |
| `call_schedule.csv` | Call dates/prices (for YTW & perpetuals) | `ISIN, CallDate, CallPrice` |
| `reference.csv` (extend, FRNs)`*` | FRN fields | `IndexType (SONIA, SOFR, etc.), FloatSpread(bps), ResetFrequency` |
| `call_schedule.csv` | Call dates/prices (for YTW & perpetuals) | `ISIN, CallDate, CallPrice` |

> *No separate `sec_PriceSP.csv` is required because Price is common to Original and S&P.*

### Calculated Output Files (wide layout)
```
sec_YTMCalc.csv
sec_EffDurationCalc.csv
sec_SpreadDurCalc.csv
sec_ZSpreadCalc.csv
sec_OASCalc.csv
sec_DMarginCalc.csv
sec_YTWCalc.csv
```
(`Calc` suffix keeps them distinct from the vendor layers.)

---

## Implementation Roadmap (each step is testable)

### ⬜ 0. Data Ingestion Plumbing
1. Confirm loader already handles `sec_Price.csv`; if not, add it (pattern identical to `sec_Spread.csv`).
2. Extend `reference.csv` parser to include new coupon & schedule fields.
3. **Unit-test:** `DataLoader.load_price()` returns non-empty DataFrame with correct dtypes.

---

### ⬜ 1. Core Bond-Math Library
* File `analytics/bond_math.py`  
  – cash-flow generator (bullet, **perpetual with horizon cap or first-call**, fixed-to-var).  
  – price ⇄ yield solver (Newton + bisection fallback).
* **Unit tests:** 5-year bullet bond; price = 100 ⇒ YTM ≈ coupon.

---

### ⬜ 2. YTM Calculation Engine
* Script: `calculators/ytm_calculator.py` – loops over all bonds & dates, writes `sec_YTMCalc.csv`.
* **UI:** Securities summary gains YTM-Calc column with 3-way toggle (Original | S&P | Calculated).
* **Test:** |Calc – Original| < 1 bp for ≥ 90 % of bonds.

---

### ⬜ 3. Effective Duration
* Finite-difference bump ±1 bp on **yield**.  
* Output `sec_EffDurationCalc.csv`.
* **Test:** Duration of zero-coupon ≈ maturity (sanity).

---

### ⬜ 4. Z-Spread Solver
* Strip zero curve if needed, solve constant spread where PV = Price.
* Output `sec_ZSpreadCalc.csv`.
* **Test:** Synthetic bond with known spread ⇒ error < 0.1 bp.

---

### ⬜ 5. Option-Adjusted Spread (OAS) Solver
* Utilises deterministic call schedule (no stochastic rates).  
* Solves constant spread over curve **after** adjusting cash-flows for optimal exercise per pricing date.  
* Output `sec_OASCalc.csv`.
* **Test:** For a non-callable bond OAS = Z-Spread within 0.1 bp.

---

### ⬜ 6. Discount Margin (DM) – Floating-Rate Notes
* Applies to bonds where `IndexType` present.  
* Uses forward curve derived from `Data/curves.csv` plus quoted **FloatSpread**.  
* Solves constant margin over reference index so PV = Price.  
* Output `sec_DMarginCalc.csv` (blank for fixed-rate bonds).  
* **Tests:** Synthetic FRN priced at par ⇒ DM ≈ quoted spread.

---

### ⬜ 7. Spread Duration
* Finite-difference on **Z-spread** (or OAS when applicable).  
* Output `sec_SpreadDurCalc.csv`.
* **Test:** Spread duration ≈ effective duration when OAS ≈ 0.

---

### ⬜ 8. Yield-to-Worst (YTW) & Perpetual Handling
* Parse `call_schedule.csv`.
* Logic:
  1. **Perpetual with Call:** Treat earliest call as pseudo-maturity for YTW, Z-Spread, OAS.
  2. **Perpetual without Call:** Use 100-year horizon for PV; yield of perp ≈ coupon/price initial guess.
* For each date: min(YTM to pseudo-maturity, YTM to each call).
* Output `sec_YTWCalc.csv`.
* **Tests:**
  * Callable > par ⇒ YTW < bullet YTM.
  * Perpetual at par with 5 % coupon ⇒ Calc YTM ≈ 5 %.

---

### ⬜ 9. Front-End Integration
1. Update `config/metric_file_map.yaml` – register Calc files.
2. Metric pages display 3-way toggle; Calculated series is colour-coded distinctly.
3. Highlight rows where `|Calc – Original| > 5 bp` (configurable).

---

### ⬜ 10. Validation Dashboard
New route `/validation/analytics`:
* Heat-map (mean & max gaps) per metric.
* Downloadable CSV of breaches.

---

### ⬜ 11. CI & Sample Data
* Mini sandbox CSVs under `tests/sample_data/`.
* CI runs pytest; fails if maths drifts > tolerance.

---

### ⬜ 12. Documentation & Training
* Update `Docs/README.md` → "Analytics Engine".
* Provide a Jupyter notebook demo for analysts.

---

## Acceptance Criteria Snapshot

| Milestone | Deliverable | Pass Condition |
|-----------|-------------|----------------|
| 0 | Price loader | DataFrame loads with correct shape |
| 2 | `sec_YTMCalc.csv` | ≥ 90 % bonds within 1 bp of Original |
| 4 | `sec_ZSpreadCalc.csv` | Spread error < 0.1 bp |
| 5 | `sec_OASCalc.csv` | OAS equals Z-Spread for bullets within 0.1 bp |
| 6 | `sec_DMarginCalc.csv` | Par FRN DM ≈ quoted spread within 0.1 bp |
| 7 | Perpetual test cases | YTM of par perpetual ≈ coupon within 0.1 bp |
| 9 | UI toggle | Users can switch between 3 layers |
| 10 | Dashboard | Breach list renders & CSV exports |

---

## Beyond MVP
* Inflation-linked cash-flows
* Perpetuals (first-call as pseudo-maturity)
* Vectorised Numpy for speed
* Real-time calculation API endpoint
