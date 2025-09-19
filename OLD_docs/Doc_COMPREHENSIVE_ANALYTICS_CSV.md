# Comprehensive Analytics CSV Generation

## Overview
The `comprehensive_analytics_%.csv` files are generated through the synth analytics processor, which calculates SpreadOMatic-based bond analytics for all securities in the system. This document describes the actual implementation as coded, not theoretical documentation.

## File Generation Process

### Entry Points

1. **Web UI**: `/api/synth_analytics/generate` endpoint (POST)
2. **Direct Python**: `synth_analytics_csv_processor.generate_comprehensive_analytics_csv()`
3. **Background Job**: Runs asynchronously via threading when triggered from web UI

### Output Filename Format
```
comprehensive_analytics_YYYYMMDD_HHMMSS.csv
```
Where:
- `YYYYMMDD` - Latest date with price data (not generation date)
- `HHMMSS` - Timestamp when generation started

## Data Sources

The processor reads from multiple CSV files in the data folder:

### Primary Data
1. **sec_Price.csv** - Main source for:
   - ISIN list
   - Latest date determination (finds most recent date column with data)
   - Clean prices
   - Security metadata (Name, Funds, Type, Callable, Currency)

### Supporting Data
2. **schedule.csv** - Bond schedule information:
   - Maturity Date
   - Issue Date  
   - Coupon Frequency
   - Day Basis
   - Call Schedule (JSON format)
   - Accrued Interest

3. **reference.csv** - Reference data (preferred source):
   - Coupon Rate (overrides schedule.csv)
   - Maturity Date (overrides schedule.csv)
   - Position Currency (overrides sec_Price Currency)
   - Call Indicator

4. **curves.csv** - Yield curve data:
   - Zero rates by currency and date
   - Terms (7D, 14D, 1M, 2M, 6M, 12M, 24M, 48M, 60M, 120M)
   - Used for spread calculations

5. **sec_accrued.csv** - Accrued interest:
   - File-based accrued interest (never calculated)
   - Used to calculate dirty price

## Processing Flow

### Step 1: Date and Security Discovery
```python
# Find latest date with price data
latest_date = most recent date column in sec_Price.csv with non-null values

# Get all securities
for each row in sec_Price.csv:
    if price exists for latest_date:
        process security
```

### Step 2: Data Assembly for Each Security
1. **Currency Determination** (priority order):
   - Position Currency from reference.csv (if exists)
   - Currency from sec_Price.csv
   - Default: 'USD'

2. **Bond Data Combination**:
   - Start with defaults
   - Override with reference.csv data (preferred)
   - Override with schedule.csv data
   - Apply sec_Price.csv metadata

3. **Default Values**:
   - Coupon Rate: 3.0%
   - Coupon Frequency: 2 (semi-annual)
   - Day Count: ACT/ACT
   - Principal: 100
   - Maturity: 5 years from valuation if missing

### Step 3: Cashflow Generation

The processor generates cashflows using SpreadOMatic's `generate_fixed_schedule`:

```python
# Key parameters
issue_date = from schedule/reference or (valuation - 1 year)
first_coupon_date = issue + (12/frequency) months
maturity_date = from data or (valuation + 5 years)
coupon_rate = from reference/schedule (as decimal)
day_basis = normalized convention
currency = determined currency
notional = 100
coupon_frequency = from data or 2

# Weekend adjustment fix applied
if final_payment == principal_only:
    add missing coupon = notional * coupon_rate / frequency
```

### Step 4: Analytics Calculation

Using SpreadOMatic functions with proper compounding:

#### Core Analytics
- **YTM**: `solve_ytm(dirty_price, times, cfs, comp=compounding)`
- **G-Spread**: `g_spread(ytm, maturity, z_times, z_rates)` - Linear interpolation
- **Z-Spread**: `z_spread(dirty_price, times, cfs, z_times, z_rates, comp=compounding)`

#### Duration Metrics
- **Effective Duration**: `effective_duration(dirty_price, times, cfs, z_times, z_rates, comp=compounding)`
- **Modified Duration**: `modified_duration(effective_duration, ytm, frequency)`
- **Spread Duration**: `effective_spread_duration(...)`
- **Convexity**: `effective_convexity(...)`

#### Key Rate Durations
Calculated for standard buckets: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y

#### OAS (if callable)
- Standard OAS using `compute_oas()` 
- Enhanced OAS using Hull-White model (if available)

#### Enhanced Analytics (if available)
- Cross Gamma
- Key Rate Convexity
- Vega (volatility sensitivity)
- Theta (time decay)

### Step 5: Output Generation

## Output Columns

### Metadata Columns
- ISIN
- Security_Name
- Funds
- Type
- Callable
- Currency
- Date (valuation date)
- Price (clean)

### Calculated Analytics
- YTM_Percent
- G_Spread_bps
- Z_Spread_bps
- Effective_Duration
- Modified_Duration
- Spread_Duration
- Convexity
- OAS_bps
- DV01
- Accrued_Interest
- Dirty_Price
- Compounding
- Enhancement_Level

### Key Rate Duration Columns
- KRD_1M through KRD_30Y (11 buckets)

### Enhanced Analytics (when available)
- OAS_Enhanced_bps
- Cross_Gamma
- Key_Rate_Convexity
- Vega
- Theta

## Important Implementation Details

### Currency Handling
The system now prioritizes Position Currency from reference.csv over the Currency field in sec_Price.csv. This ensures consistency with Excel calculations.

### Accrued Interest
ALWAYS loaded from sec_accrued.csv file. Never calculated. If not found, defaults to 0.

### Day Count Conventions
Normalized mappings:
- 30E/360 variants → "30E/360" 
- 30/360-US variants → "30/360"
- ACT/ACT variants → "ACT/ACT"
- ACT/365 variants → "ACT/365"
- ACT/360 variants → "ACT/360"

### Compounding
- Semi-annual: When coupon frequency = 2
- Annual: All other cases
- Never continuous (despite some legacy code references)

### Weekend Maturity Bug Fix
When bond maturity falls on weekend and business day adjustment separates principal from final coupon:
- Detects principal-only payment (amount ≈ 100)
- Adds missing coupon: notional × coupon_rate / frequency

### Error Handling
- Securities with missing prices are skipped
- Securities with invalid data get NaN values for all analytics
- Curve data fallbacks: Uses any available curve for currency if date-specific not found
- Processing continues even if individual securities fail

## Performance Characteristics

- Processes approximately 50 securities per second
- Logs progress every 50 securities
- Runs in background thread when triggered from web UI
- Full dataset (~1000 securities) takes 20-30 seconds

## File Location
Generated files are saved to the configured data folder (from settings.yaml), typically:
```
C:\Users\[username]\Code\Simple Data Checker\Data\comprehensive_analytics_YYYYMMDD_HHMMSS.csv
```

## Usage Example

### Via Python:
```python
from analytics.synth_analytics_csv_processor import generate_comprehensive_analytics_csv

success, message, output_path = generate_comprehensive_analytics_csv(
    data_folder="Data",
    output_filename="custom_analytics.csv"  # Optional
)
```

### Via Web API:
```javascript
POST /api/synth_analytics/generate
{
    "output_filename": "custom_name.csv"  // Optional
}
```

## Validation

To verify calculations match Excel:
1. Run `compare_calculations.py` for specific ISINs
2. Check that YTM, Z-spread, and G-spread match within tolerance
3. Verify currency selection matches (Position Currency takes precedence)
4. Confirm accrued interest comes from file, not calculation