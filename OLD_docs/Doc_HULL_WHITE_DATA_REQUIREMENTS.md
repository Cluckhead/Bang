# Hull-White OAS Model - Complete Data Requirements Specification

## Executive Summary

This document specifies all data requirements to fully utilize the Hull-White Option-Adjusted Spread (OAS) calculation capabilities in the SpreadOMatic system. The Hull-White model is an industry-standard one-factor interest rate model that requires specific market data for accurate calibration and computation.

## Current vs. Optimal Implementation

### Current State (Limited Data)
- **Functionality**: Operational with hardcoded parameters
- **Accuracy**: ±10-50 basis points uncertainty
- **Parameters**: Fixed mean reversion (0.1) and volatility (1.5%)

### Optimal State (Full Data)
- **Functionality**: Market-calibrated parameters
- **Accuracy**: ±2-5 basis points uncertainty
- **Parameters**: Daily calibration to market observables

---

## 1. Core Bond Data Requirements

### 1.1 Security Master Data
```csv
# Format: security_master.csv
ISIN,SecurityName,IssuerName,Currency,IssueDate,MaturityDate,CouponRate,CouponFrequency,DayCountBasis,Rating,Sector,Country,IssueSize
US912828YY18,UST 2.5% 2029,US Treasury,USD,2019-05-15,2029-05-15,2.5,2,ACT/ACT,AAA,Government,USA,50000000000
XS1234567890,CORP 4% 2030,ABC Corp,EUR,2020-01-15,2030-01-15,4.0,2,30/360,BBB,Corporate,USA,1000000000
```

### 1.2 Call Schedule Data
```csv
# Format: call_schedule.csv
ISIN,CallDate,CallPrice,CallType,NoticePeroidDays,MakeWholeSpread
XS1234567890,2025-01-15,100.0,AMERICAN,30,
XS1234567890,2026-01-15,100.0,AMERICAN,30,
XS1234567890,2027-01-15,100.0,AMERICAN,30,
US345678AB12,2024-06-01,102.5,EUROPEAN,45,50
```

**CallType Options**:
- `AMERICAN`: Continuous exercise
- `EUROPEAN`: Single date exercise
- `BERMUDAN`: Multiple discrete dates
- `MAKE_WHOLE`: Make-whole call provision

### 1.3 Payment Schedule
```csv
# Format: payment_schedule.csv
ISIN,PaymentDate,CouponAmount,PrincipalAmount,AccrualDays,AccrualFraction
US912828YY18,2024-05-15,1.25,0,182,0.4986
US912828YY18,2024-11-15,1.25,0,184,0.5041
US912828YY18,2025-05-15,1.25,0,181,0.4959
```

---

## 2. Market Data Requirements

### 2.1 Bond Pricing Data
```csv
# Format: bond_prices.csv
Date,ISIN,PriceType,Price,Yield,Volume,Source
2024-01-15,US912828YY18,CLEAN,98.50,2.75,1000000,TRACE
2024-01-15,US912828YY18,DIRTY,99.35,2.75,1000000,TRACE
2024-01-15,XS1234567890,CLEAN,102.25,3.65,500000,TRACE
```

**PriceType Requirements**:
- Both CLEAN and DIRTY prices needed
- Mid, Bid, and Ask prices for spread calculation
- Volume data for liquidity adjustment

### 2.2 Yield Curve Data
```csv
# Format: yield_curves.csv
Date,Currency,Tenor,TenorDays,Rate,RateType,Source
2024-01-15,USD,1M,30,5.25,ZERO,FED
2024-01-15,USD,3M,91,5.30,ZERO,FED
2024-01-15,USD,6M,182,5.35,ZERO,FED
2024-01-15,USD,1Y,365,5.20,ZERO,FED
2024-01-15,USD,2Y,730,4.80,ZERO,FED
2024-01-15,USD,3Y,1095,4.60,ZERO,FED
2024-01-15,USD,5Y,1825,4.40,ZERO,FED
2024-01-15,USD,7Y,2555,4.35,ZERO,FED
2024-01-15,USD,10Y,3650,4.30,ZERO,FED
2024-01-15,USD,20Y,7300,4.50,ZERO,FED
2024-01-15,USD,30Y,10950,4.60,ZERO,FED
```

**Required Curves**:
- Government curve (risk-free)
- Swap curve (for spread calculation)
- Credit curves by rating (AAA, AA, A, BBB, etc.)
- OIS curve (for discounting)

---

## 3. Volatility Data Requirements (CRITICAL)

### 3.1 Swaption Volatility Surface
```csv
# Format: swaption_volatilities.csv
Date,Currency,OptionTenor,SwapTenor,Strike,ImpliedVol,VolType,Moneyness,Source
2024-01-15,USD,1M,1Y,ATM,0.850,NORMAL,1.00,ICAP
2024-01-15,USD,1M,2Y,ATM,0.820,NORMAL,1.00,ICAP
2024-01-15,USD,1M,5Y,ATM,0.780,NORMAL,1.00,ICAP
2024-01-15,USD,1M,10Y,ATM,0.750,NORMAL,1.00,ICAP
2024-01-15,USD,3M,1Y,ATM,0.880,NORMAL,1.00,ICAP
2024-01-15,USD,3M,2Y,ATM,0.850,NORMAL,1.00,ICAP
2024-01-15,USD,3M,5Y,ATM,0.800,NORMAL,1.00,ICAP
2024-01-15,USD,3M,10Y,ATM,0.770,NORMAL,1.00,ICAP
2024-01-15,USD,6M,1Y,ATM,0.900,NORMAL,1.00,ICAP
2024-01-15,USD,6M,2Y,ATM,0.870,NORMAL,1.00,ICAP
2024-01-15,USD,6M,5Y,ATM,0.820,NORMAL,1.00,ICAP
2024-01-15,USD,6M,10Y,ATM,0.790,NORMAL,1.00,ICAP
2024-01-15,USD,1Y,1Y,ATM,0.920,NORMAL,1.00,ICAP
2024-01-15,USD,1Y,2Y,ATM,0.890,NORMAL,1.00,ICAP
2024-01-15,USD,1Y,5Y,ATM,0.840,NORMAL,1.00,ICAP
2024-01-15,USD,1Y,10Y,ATM,0.810,NORMAL,1.00,ICAP
2024-01-15,USD,2Y,2Y,ATM,0.910,NORMAL,1.00,ICAP
2024-01-15,USD,2Y,5Y,ATM,0.860,NORMAL,1.00,ICAP
2024-01-15,USD,2Y,10Y,ATM,0.830,NORMAL,1.00,ICAP
2024-01-15,USD,5Y,5Y,ATM,0.880,NORMAL,1.00,ICAP
2024-01-15,USD,5Y,10Y,ATM,0.850,NORMAL,1.00,ICAP
```

**Required Coverage**:
- Minimum grid: [1M, 3M, 6M, 1Y, 2Y, 5Y] × [1Y, 2Y, 5Y, 10Y, 20Y, 30Y]
- Strike coverage: ATM, ±25bp, ±50bp, ±100bp
- Update frequency: Daily for liquid pairs, weekly for others

### 3.2 Cap/Floor Volatilities
```csv
# Format: cap_floor_volatilities.csv
Date,Currency,Tenor,Strike,ImpliedVol,VolType,InstrumentType,Source
2024-01-15,USD,1Y,2.00,1.20,LOGNORMAL,CAP,Bloomberg
2024-01-15,USD,1Y,3.00,1.00,LOGNORMAL,CAP,Bloomberg
2024-01-15,USD,1Y,4.00,0.85,LOGNORMAL,CAP,Bloomberg
2024-01-15,USD,2Y,2.00,1.10,LOGNORMAL,CAP,Bloomberg
2024-01-15,USD,2Y,3.00,0.95,LOGNORMAL,CAP,Bloomberg
2024-01-15,USD,2Y,4.00,0.82,LOGNORMAL,CAP,Bloomberg
```

### 3.3 Callable Bond Implied Volatilities
```csv
# Format: callable_bond_implied_vols.csv
Date,ISIN,TimeToFirstCall,OAS,ImpliedVol,Method,Source
2024-01-15,XS1234567890,1.0,0.0050,0.15,BLACK,Internal
2024-01-15,US345678AB12,0.5,0.0075,0.18,BLACK,Internal
```

---

## 4. Historical Data for Calibration

### 4.1 Historical Yield Curves (Minimum 5 Years)
```csv
# Format: historical_yield_curves.csv
Date,Currency,1M,3M,6M,1Y,2Y,3Y,5Y,7Y,10Y,20Y,30Y
2019-01-15,USD,2.40,2.45,2.55,2.60,2.55,2.50,2.48,2.50,2.55,2.70,2.80
2019-01-16,USD,2.41,2.46,2.56,2.61,2.54,2.49,2.47,2.49,2.54,2.69,2.79
# ... daily data for 5+ years
```

**Usage**: 
- Estimate mean reversion parameter (a)
- Calculate historical volatility
- Validate model stability

### 4.2 Historical Volatilities
```csv
# Format: historical_volatilities.csv
Date,Currency,Tenor,RealizedVol30D,RealizedVol90D,RealizedVol1Y
2024-01-15,USD,2Y,0.0080,0.0075,0.0082
2024-01-15,USD,5Y,0.0072,0.0070,0.0076
2024-01-15,USD,10Y,0.0068,0.0065,0.0070
2024-01-15,USD,30Y,0.0065,0.0062,0.0068
```

---

## 5. Credit and Spread Data

### 5.1 Credit Spreads by Rating
```csv
# Format: credit_spreads.csv
Date,Rating,Sector,Tenor,Spread,Source
2024-01-15,AAA,Corporate,5Y,0.0020,TRACE
2024-01-15,AA,Corporate,5Y,0.0035,TRACE
2024-01-15,A,Corporate,5Y,0.0055,TRACE
2024-01-15,BBB,Corporate,5Y,0.0095,TRACE
2024-01-15,BB,Corporate,5Y,0.0250,TRACE
```

### 5.2 Sector Spreads
```csv
# Format: sector_spreads.csv
Date,Sector,Rating,AverageSpread,MedianSpread,StdDev
2024-01-15,Financials,A,0.0065,0.0060,0.0015
2024-01-15,Industrials,A,0.0055,0.0052,0.0012
2024-01-15,Utilities,A,0.0045,0.0043,0.0008
```

---

## 6. Market Convention Data

### 6.1 Day Count Conventions
```csv
# Format: market_conventions.csv
Currency,InstrumentType,DayCountBasis,CompoundingFrequency,SettlementDays
USD,Treasury,ACT/ACT,2,1
USD,Corporate,30/360,2,2
EUR,Government,ACT/ACT,1,2
EUR,Corporate,30/360,1,2
GBP,Gilt,ACT/365,2,1
```

### 6.2 Holiday Calendars
```csv
# Format: holidays.csv
Date,Currency,HolidayName,MarketStatus
2024-01-01,USD,New Year's Day,CLOSED
2024-01-15,USD,Martin Luther King Jr. Day,CLOSED
2024-02-19,USD,Presidents Day,CLOSED
```

---

## 7. Model Calibration Parameters

### 7.1 Hull-White Parameters
```json
{
  "calibration_date": "2024-01-15",
  "currency": "USD",
  "parameters": {
    "mean_reversion": {
      "value": 0.1,
      "standard_error": 0.02,
      "confidence_interval": [0.06, 0.14],
      "calibration_method": "MLE",
      "data_period": "2019-01-01 to 2024-01-15"
    },
    "volatility": {
      "value": 0.015,
      "standard_error": 0.002,
      "confidence_interval": [0.011, 0.019],
      "calibration_method": "SWAPTION_IMPLIED",
      "calibration_instruments": ["1Yx10Y", "2Yx10Y", "5Yx10Y"]
    },
    "theta_function": {
      "type": "piecewise_constant",
      "values": [
        {"tenor": 0.25, "value": 0.05},
        {"tenor": 0.50, "value": 0.051},
        {"tenor": 1.00, "value": 0.052},
        {"tenor": 2.00, "value": 0.048},
        {"tenor": 5.00, "value": 0.045}
      ]
    }
  },
  "calibration_quality": {
    "rmse": 0.0012,
    "max_error": 0.0035,
    "instruments_used": 45,
    "instruments_fitted": 43
  }
}
```

### 7.2 Alternative Model Parameters
```json
{
  "black_karasinski": {
    "mean_reversion": 0.15,
    "volatility": 0.20
  },
  "cox_ingersoll_ross": {
    "mean_reversion": 0.10,
    "long_term_mean": 0.04,
    "volatility": 0.08
  },
  "two_factor_hull_white": {
    "mean_reversion_1": 0.10,
    "mean_reversion_2": 0.01,
    "volatility_1": 0.015,
    "volatility_2": 0.008,
    "correlation": -0.7
  }
}
```

---

## 8. Real-Time Data Feeds

### 8.1 Required Data Vendors
- **Bloomberg Terminal**: Real-time prices, yields, volatilities
- **Refinitiv (Reuters)**: Swaption volatilities, credit spreads
- **ICE Data Services**: Bond prices, yield curves
- **TRACE**: Corporate bond transactions
- **MSRB EMMA**: Municipal bond data

### 8.2 API Endpoints
```yaml
data_sources:
  bloomberg:
    endpoint: "https://api.bloomberg.com/data/v1/"
    fields:
      - PX_LAST
      - YLD_YTM_MID
      - VOLATILITY_90D
      - OAS_SPREAD_BID
    update_frequency: "real-time"
  
  refinitiv:
    endpoint: "https://api.refinitiv.com/data/v1/"
    fields:
      - TR.SWAPTIONVOLATILITY
      - TR.CREDITSPREAD
      - TR.YIELDCURVE
    update_frequency: "15-minute"
  
  ice_data:
    endpoint: "https://api.theice.com/bond-data/v1/"
    fields:
      - CLEAN_PRICE
      - ACCRUED_INTEREST
      - Z_SPREAD
    update_frequency: "end-of-day"
```

---

## 9. Data Quality Requirements

### 9.1 Validation Rules
```yaml
validation_rules:
  prices:
    - range: [50, 150]  # Percentage of par
    - max_daily_change: 10  # Percent
    - staleness_threshold: 5  # Business days
  
  yields:
    - range: [-0.02, 0.20]  # -2% to 20%
    - max_daily_change: 0.01  # 100 basis points
    - curve_monotonicity: false  # Allow inversions
  
  volatilities:
    - range: [0.0001, 2.0]  # 1bp to 200%
    - max_daily_change: 0.50  # 50% relative change
    - surface_arbitrage_free: true
```

### 9.2 Data Completeness Metrics
```yaml
required_completeness:
  yield_curve:
    minimum_tenors: 11
    required_tenors: [1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y]
    interpolation_method: "cubic_spline"
  
  volatility_surface:
    minimum_points: 20
    required_grid: 
      option_tenors: [1M, 3M, 6M, 1Y, 2Y, 5Y]
      swap_tenors: [1Y, 2Y, 5Y, 10Y, 20Y, 30Y]
    extrapolation_method: "flat"
  
  historical_data:
    minimum_history: 1260  # 5 years of business days
    maximum_gaps: 5  # Consecutive missing days
    gap_filling_method: "linear_interpolation"
```

---

## 10. Implementation Checklist

### Phase 1: Basic Implementation (Current State)
- [x] Bond reference data
- [x] Basic yield curves
- [x] Bond prices
- [x] Call schedules
- [ ] Swaption volatilities
- [ ] Historical yield data

### Phase 2: Enhanced Calibration
- [ ] Complete swaption volatility surface
- [ ] Historical volatility data
- [ ] Credit spread curves
- [ ] Parameter estimation framework
- [ ] Model validation suite

### Phase 3: Production Ready
- [ ] Real-time data feeds
- [ ] Automated calibration
- [ ] Model performance monitoring
- [ ] Volatility smile modeling
- [ ] Multi-factor models

### Phase 4: Advanced Features
- [ ] Stochastic volatility models
- [ ] Jump diffusion components
- [ ] Regime switching models
- [ ] Machine learning enhancements
- [ ] Cross-asset correlations

---

## 11. Data Storage Requirements

### 11.1 Database Schema
```sql
-- Core tables
CREATE TABLE bond_master (
    isin VARCHAR(12) PRIMARY KEY,
    security_name VARCHAR(255),
    issuer_name VARCHAR(255),
    issue_date DATE,
    maturity_date DATE,
    coupon_rate DECIMAL(10,6),
    coupon_frequency INT,
    day_count_basis VARCHAR(20)
);

CREATE TABLE call_schedule (
    id INT PRIMARY KEY AUTO_INCREMENT,
    isin VARCHAR(12),
    call_date DATE,
    call_price DECIMAL(10,4),
    call_type VARCHAR(20),
    FOREIGN KEY (isin) REFERENCES bond_master(isin)
);

CREATE TABLE market_data (
    date DATE,
    isin VARCHAR(12),
    clean_price DECIMAL(10,4),
    dirty_price DECIMAL(10,4),
    yield DECIMAL(10,6),
    z_spread DECIMAL(10,6),
    oas DECIMAL(10,6),
    PRIMARY KEY (date, isin)
);

CREATE TABLE yield_curves (
    date DATE,
    currency VARCHAR(3),
    tenor DECIMAL(10,4),
    rate DECIMAL(10,6),
    curve_type VARCHAR(20),
    PRIMARY KEY (date, currency, tenor, curve_type)
);

CREATE TABLE swaption_volatilities (
    date DATE,
    currency VARCHAR(3),
    option_tenor DECIMAL(10,4),
    swap_tenor DECIMAL(10,4),
    strike VARCHAR(20),
    implied_vol DECIMAL(10,6),
    PRIMARY KEY (date, currency, option_tenor, swap_tenor, strike)
);
```

### 11.2 File Storage Structure
```
/data
├── /static
│   ├── /bond_master
│   ├── /call_schedules
│   └── /market_conventions
├── /market_data
│   ├── /prices
│   │   ├── /2024
│   │   │   ├── /01
│   │   │   │   ├── prices_2024-01-15.csv
│   │   │   │   └── ...
│   ├── /yield_curves
│   └── /volatilities
├── /historical
│   ├── /yield_curves
│   ├── /volatilities
│   └── /spreads
└── /calibration
    ├── /parameters
    ├── /validation
    └── /backtest
```

---

## 12. Performance Benchmarks

### 12.1 Calculation Speed Requirements
- Single bond OAS: < 100ms
- Portfolio (100 bonds): < 10 seconds
- Full recalibration: < 5 minutes

### 12.2 Accuracy Targets
- OAS accuracy: ±2 basis points
- Option value: ±0.5% of notional
- Duration: ±0.05 years
- Convexity: ±2.0

---

## Appendix A: Sample Data Files

All sample data files can be found in the `/sample_data` directory with complete examples for:
- 10 callable bonds with full schedules
- 5 years of daily yield curves
- Complete swaption volatility surface
- Historical calibration parameters

## Appendix B: Vendor Contacts

| Vendor | Product | Contact | Cost Estimate |
|--------|---------|---------|--------------|
| Bloomberg | Terminal + API | enterprise@bloomberg.com | $24,000/year/terminal |
| Refinitiv | Eikon + DataScope | sales@refinitiv.com | $20,000/year/user |
| ICE Data | BondEdge | sales@theice.com | $15,000/year/user |
| ICAP | Swaption Vol Data | data@icap.com | $10,000/year |

## Appendix C: Regulatory Compliance

Ensure compliance with:
- FRTB (Fundamental Review of the Trading Book)
- IFRS 13 / ASC 820 (Fair Value Measurement)
- Solvency II (for European insurers)
- NAIC guidelines (for US insurers)

---

*Document Version: 1.0*  
*Last Updated: 2024*  
*Next Review: Quarterly*