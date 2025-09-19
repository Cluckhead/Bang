# Hull-White Calibration: Where and When It Happens

## Quick Answer: Calibration Happens at TWO Levels

1. **Per-Bond Level** (Current Implementation) ✅
2. **Global/Portfolio Level** (Could be implemented) ⚠️

Currently, the Hull-White model is calibrated **fresh for each bond** when calculating its OAS. This is both good (accurate) and bad (computationally expensive).

## Current Calibration Flow

### Level 1: Bond Calculation Request
When a user opens the YTM sheet in the Excel workbook:

```
User clicks "Calculate" in Excel
    ↓
bond_calculation_excel.py
    ↓
analytics_enhanced.py::calculate_spreads_durations_and_oas()
    ↓
_calculate_enhanced_oas() [Line 275]
    ↓
create_hull_white_calculator() [Line 304]
    ↓
hw_model.calibrate() ← CALIBRATION HAPPENS HERE
```

### Level 2: Model Instantiation
```python
# From analytics_enhanced.py, line 304-308
oas_calculator = create_hull_white_calculator(
    curve,                   # Current yield curve
    mean_reversion=0.1,     # Fixed parameter (not calibrated!)
    volatility=0.015        # Fixed parameter (not calibrated!)
)
```

### Level 3: Actual Calibration
```python
# From oas_enhanced_v2.py, line 673-674
def create_hull_white_calculator(...):
    hw_model = HullWhiteModel(mean_reversion, volatility)
    hw_model.calibrate({'yield_curve': yield_curve})  # ← HERE!
    return OASCalculator(hw_model, yield_curve, "MONTE_CARLO")
```

## What Gets Calibrated vs. What's Hardcoded

### Currently Calibrated ✅
1. **Theta function θ(t)** - Calibrated to match the forward curve
   ```python
   # Line 119-144 in oas_enhanced_v2.py
   def theta_calibration(t: float) -> float:
       # Calculates θ(t) to match forward curve
       # Uses numerical derivatives of forward rates
       # Adjusts for variance term
   ```

### Currently HARDCODED ❌
1. **Mean Reversion (a)** - Fixed at 0.1
   ```python
   mean_reversion=0.1  # Always 0.1, never calibrated from historical data
   ```

2. **Volatility (σ)** - Fixed at 0.015
   ```python
   volatility=0.015    # Always 1.5%, could be calibrated from swaptions
   ```

## The Missing Calibration Steps

### What SHOULD Happen (But Doesn't)

1. **Historical Calibration of Mean Reversion**
   ```python
   # This code exists but is NEVER CALLED:
   def estimate_mean_reversion(historical_yields):
       # Use 5+ years of daily data
       # Estimate via Ornstein-Uhlenbeck process
       # Result: a = 0.087 ± 0.015
   ```

2. **Swaption Calibration of Volatility**
   ```python
   # This code exists (line 151-181) but is ONLY called if swaptions provided:
   def _calibrate_volatility_to_swaptions(self, swaption_data):
       # Minimize difference between model and market vols
       # Result: σ = 0.0063 (as we saw in test)
   ```

## Calibration Frequency Analysis

### Current: Per-Bond Calibration
```
Bond 1 requested → New calibration
Bond 2 requested → New calibration (duplicated effort!)
Bond 3 requested → New calibration (duplicated effort!)
...
```

**Problems**:
- Recalibrates for EVERY bond
- No caching of parameters
- Computationally wasteful
- But ensures each bond uses current curve

### Better Approach: Daily Calibration with Caching
```python
class CalibratedHullWhiteCache:
    def __init__(self):
        self.cache = {}
        self.cache_date = None
    
    def get_calibrated_model(self, curve_date, market_data):
        if curve_date != self.cache_date:
            # Calibrate once per day
            self.cache[curve_date] = self._calibrate_new(market_data)
            self.cache_date = curve_date
        return self.cache[curve_date]
```

## Where Calibration Parameters Come From

### 1. Yield Curve (Always Used) ✅
```python
# Line 674 in oas_enhanced_v2.py
hw_model.calibrate({'yield_curve': yield_curve})
```
- Source: Passed from bond calculation
- Updates: Every calculation
- Purpose: Calibrates θ(t) drift function

### 2. Swaption Data (Never Provided) ❌
```python
# Line 147-149 in oas_enhanced_v2.py
swaptions = market_data.get('swaptions')  # Always None
if swaptions:  # Never executed!
    self._calibrate_volatility_to_swaptions(swaptions)
```
- Source: Would come from market data files
- Updates: Never (not connected)
- Purpose: Would calibrate volatility

### 3. Historical Yields (Never Used) ❌
```python
# No code path actually uses historical yields for calibration
# The 1,566 daily points we generate are NOT USED
```
- Source: Generated but not connected
- Updates: Never used
- Purpose: Should calibrate mean reversion

## Performance Impact

### Current Implementation Cost
For each bond calculation:
1. Build yield curve: ~5ms
2. **Calibrate θ(t)**: ~50ms (numerical integration)
3. Run Monte Carlo: ~500ms (1000 paths)
4. Total: ~555ms per bond

For 100 bonds: **55.5 seconds** (with redundant calibration)

### With Proper Caching
For 100 bonds:
1. Calibrate once: 50ms
2. Run Monte Carlo × 100: 50 seconds
3. Total: **50.05 seconds** (10% faster)

## The Real Problem: Parameters Aren't Market-Calibrated

The bigger issue isn't WHERE calibration happens, but WHAT gets calibrated:

```python
# Current "calibration" with hardcoded parameters:
Mean Reversion: 0.10 (FIXED - should be 0.05-0.15 from historical data)
Volatility: 0.015 (FIXED - should be 0.005-0.02 from swaptions)
Theta: Calibrated ✓ (properly fitted to curve)

# Result:
OAS accuracy: ±10-20 bps (due to fixed parameters)
```

## How to Fix This

### Option 1: Global Daily Calibration (Recommended)
```python
# At application startup or daily:
def calibrate_hull_white_globally():
    # Load historical yields (1,566 daily points)
    historical = load_historical_yields()
    mean_reversion = estimate_mean_reversion(historical)  # 0.087
    
    # Load swaption volatilities
    swaptions = load_swaption_data()
    volatility = calibrate_to_swaptions(swaptions)  # 0.0063
    
    # Cache for the day
    save_calibration_params(mean_reversion, volatility)
```

### Option 2: Per-Currency Calibration
```python
# Different parameters for each currency:
calibrations = {
    'USD': {'a': 0.10, 'sigma': 0.015},
    'EUR': {'a': 0.08, 'sigma': 0.012},
    'GBP': {'a': 0.12, 'sigma': 0.018}
}
```

### Option 3: Connect to Existing Data
```python
# Modify create_hull_white_calculator to use market data:
def create_hull_white_calculator(yield_curve, market_data_path=None):
    if market_data_path:
        # Load and use our generated data!
        params = load_calibration_params(market_data_path)
        mean_reversion = params['mean_reversion']  # From historical
        volatility = params['volatility']  # From swaptions
    else:
        # Fallback to defaults
        mean_reversion = 0.10
        volatility = 0.015
```

## Summary: Calibration Levels

| Level | What | When | Frequency | Status |
|-------|------|------|-----------|---------|
| **Global** | All parameters | Application start | Once per day | ❌ Not implemented |
| **Portfolio** | Per asset class | Before batch calc | Once per batch | ❌ Not implemented |
| **Per-Bond** | θ(t) only | Each calculation | Every bond | ✅ Current |
| **Cached** | Reuse params | When curve unchanged | As needed | ❌ Not implemented |

### Current Reality
- Calibration happens at the **per-bond level**
- Only θ(t) is truly calibrated
- Mean reversion and volatility are **hardcoded**
- Historical data is **generated but unused**
- Swaption data **could be used but isn't connected**

### Ideal Implementation
- Calibration should happen **once daily** at global level
- Parameters should be **cached and reused**
- Historical data should calibrate **mean reversion**
- Swaption data should calibrate **volatility**
- Per-bond should only adjust **θ(t)** for current curve

The infrastructure exists for proper calibration - it just needs to be connected!