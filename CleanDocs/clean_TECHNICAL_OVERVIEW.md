## Technical Overview for Agents & Developers

### 1. Project Objective

Provide a reliable, configurable toolkit to ingest, validate, and analyze fixed‑income data; surface quality issues early; and present transparent analytics through a Flask web UI.

### 2. System Architecture

Simple Data Checker is a comprehensive, Flask-based web application designed to ingest, validate, and analyse financial data sets, with a particular emphasis on time-series and security-level data for fixed income analytics.

**High-Level Architecture:**
- Flask web server exposes dashboards and tools (entry: `app.py`)
- Backend processing modules perform ingestion, preprocessing, analytics, and quality checks (e.g., `run_all_checks.py`)
- Central configuration via `settings.yaml` and optional overrides in `config/` loaded by `settings_loader.py`
- Data lives in `Data/` as CSVs; outputs (e.g., `dashboard_kpis.json`) power the UI

At its core, Simple Data Checker follows a modular, configuration-driven model. It ingests data primarily from CSV files, which are pre-processed and stored in a standardised format under a central data directory (`Data/`). These files are then loaded, audited, and analysed through a set of well-structured backend services, exposing their output through a modern web interface, built with Tailwind CSS for consistency and clarity.

**Data Flow Overview:**

1. **Raw Data Processing**: Raw data files are batch-processed by a dedicated pre-processing pipeline (`preprocessing.py` and `run_preprocessing.py`). This includes:
   - Header/date normalisation
   - Aggregation
   - Metadata enrichment
   - Conversion from long- to wide-form or vice versa

2. **Data Loading**: Processed data are loaded by feature-specific modules:
   - `data_loader.py`
   - `security_processing.py` 
   - `curve_processing.py`

3. **Validation and Auditing**: Run both at ingestion (via `data_validation.py`) and on demand (`data_audit.py`), ensuring structure and content integrity.

4. **Analysis Logic**: Specialist modules handle:
   - Calculation of metrics
   - Z-scores
   - Staleness detection
   - Comparison statistics
   - Attribution breakdowns
   - File delivery health monitoring

5. **UI Rendering**: Performed via structured Jinja2 templates, JavaScript modules, and central navigation config.

### 3. Directory Structure (detailed)

#### Core Application Structure
```
├── app.py                          # Flask app factory and routing bootstrap
├── CLAUDE.md                       # Project guidance for AI agents
├── settings.yaml                   # Main application configuration
└── requirements.txt                # Python dependencies
```

#### Core Modules
```
core/
├── config.py                       # Application constants and configuration loading
├── utils.py                        # Common utility functions  
├── navigation_config.py            # UI navigation structure
├── data_loader.py                  # Core data loading utilities
├── data_utils.py                   # CSV reading and data transformation utilities
├── io_lock.py                      # File locking for concurrent CSV operations
├── settings_loader.py              # Settings management from YAML files
└── settlement_utils.py             # Settlement date calculations
```

#### Analytics & Processing (`analytics/`)
```
analytics/
├── security_data_provider.py      # **NEW** - Unified data layer for consistent calculations
├── synth_spread_calculator.py     # SpreadOMatic calculations (refactored)
├── synth_analytics_csv_processor.py # Comprehensive analytics generation (refactored)
├── metric_calculator.py           # Statistical metrics and Z-scores
├── security_processing.py         # Security-level analytics
├── staleness_processing.py        # Stale data detection
├── maxmin_processing.py           # Threshold breach detection
├── file_delivery_processing.py    # File delivery monitoring
├── issue_processing.py            # Issue tracking management
├── ticket_processing.py           # Automated ticket generation
├── curve_processing.py             # Yield curve data processing (moved from analytics/)
└── price_matching_processing.py    # Price comparison between sources
```

#### Data Processing & Validation (`data_processing/`)
```
data_processing/
├── data_validation.py              # Data validation routines
├── data_audit.py                   # Data consistency auditing
├── preprocessing.py                # Data preprocessing pipeline
├── curve_processing.py             # Yield curve data processing
└── price_matching_processing.py   # Price comparison between sources
```

#### Configuration System
```
├── settings.yaml                   # Main application configuration (includes all configs)
└── config/
    └── settlement_conventions.yaml # Settlement date conventions
```

Note: Configuration sections previously listed as separate YAML files are embedded in `settings.yaml`:
- `metric_file_map`: Metric to file mappings
- `file_delivery`: File delivery monitor configuration  
- `maxmin_thresholds`: Threshold breach limits
- `attribution_columns`: Attribution factor mappings
- `date_patterns`: Date parsing patterns
- `field_aliases`: Field name standardization
- `comparison_config`: Comparison view configuration

#### Flask Application (`views/`)
```
views/
├── main_views.py                  # Dashboard and main navigation routes
├── api_views.py                    # Core API infrastructure  
├── api_core.py                     # Core API functionality
├── api_routes_data.py              # Data API routes
├── api_routes_call.py              # Call API routes
├── security_views.py               # Security analysis pages
├── fund_views.py                   # Fund analysis and details
├── metric_views.py                 # Time-series metric views
├── attribution_views.py            # Attribution analysis dashboards
├── attribution_processing.py       # Attribution data processing
├── attribution_cache.py            # Attribution caching system
├── curve_views.py                  # Yield curve analysis
├── generic_comparison_views.py     # Configurable comparison engine
├── comparison_helpers.py           # Comparison utilities
├── security_helpers.py             # Security data helpers
├── ticket_views.py                # Automated ticketing system
├── issue_views.py                 # Issue tracking and management
├── watchlist_views.py             # Security watchlist management
├── exclusion_views.py             # Security exclusion management
├── maxmin_views.py                # Threshold breach dashboards
├── staleness_views.py             # Stale data detection views
├── file_delivery_views.py         # File delivery monitoring
├── price_matching_views.py        # Price comparison views
├── search_views.py                # Security search functionality
├── weight_views.py                # Portfolio weight analysis
├── inspect_views.py               # Data inspection tools
├── settings_views.py              # Settings management UI
├── synth_analytics_api.py         # Synthetic analytics API
├── krd_views.py                   # Key Rate Duration views
└── bond_calc_views.py             # Bond calculator and analytics debug workstation
```

#### Templates & Static Assets
```
templates/                         # Jinja2 HTML templates
├── base.html                     # Base template with navigation
├── index.html                    # Main dashboard
├── security_*.html               # Security analysis pages
├── fund_*.html                   # Fund analysis pages
├── attribution_*.html            # Attribution dashboards
├── comparison_*.html             # Generic comparison templates
├── tickets_page.html             # Ticket management interface
├── issues_page.html              # Issue tracking interface
└── debug_workstation/            # Bond analytics debug interface
    └── analytics_debug.html      # Enhanced 7-panel debug workstation

static/
├── css/
│   └── tailwind.css              # Compiled Tailwind CSS
├── js/
│   ├── main.js                   # Core JavaScript functionality
│   └── modules/                  # Modular JavaScript components
│       ├── ui/                   # UI components (charts, tables, filters)
│       ├── utils/                # Utility functions and helpers
│       └── charts/               # Chart-specific modules
└── images/                       # Application assets and icons
```

#### Testing Infrastructure (`tests/`)
```
tests/
├── conftest.py                   # Pytest configuration and fixtures
├── test_create_app.py           # Flask application factory tests
├── test_security_data_provider.py # SecurityDataProvider comprehensive tests (28 tests)
├── test_integration_unified_provider.py # Integration validation tests
├── test_fixed_income_harness.py # Bond analytics validation suite
├── test_load_and_process_data.py # Data loading tests
├── test_data_validation.py      # Data validation tests
├── test_metric_calculator.py    # Metrics calculation tests
├── test_ticket_processing.py    # Ticket system tests
└── [component_tests]/           # Individual component test files
```

#### Tools & Utilities (`tools/`)
```
tools/
├── run_preprocessing.py            # Batch preprocessing script
├── run_all_checks.py               # Orchestrates all data quality checks
├── populate_attribution_cache.py   # Attribution cache management
├── staleness_detection.py          # Standalone staleness analysis
├── setup_installer.py              # Desktop application installer
├── create_shortcuts.py             # Windows shortcut creation
├── markdown_combiner.py            # Documentation consolidation tool
├── excel_to_csvs.py                # Excel to CSV conversion
├── data_extender.py                # Data extension utilities
├── verify_synth_vs_comprehensive.py # Synthetic output validation
├── diagnose_zspread_diff.py        # Z-spread diagnostic tool
├── generate_hull_white_market_data.py # Hull-White calibration data generator
└── SpreadOMatic/                   # SpreadOMatic bond analytics engine
```

#### Data Storage (`Data/`)
```
Data/
├── ts_*.csv                     # Time-series data (long format)
├── sp_ts_*.csv                  # S&P comparison time-series
├── sec_*.csv                    # Security-level data (wide format)  
├── sec_*SP.csv                  # S&P security-level overlays
├── synth_sec_*.csv             # Synthetic analytics outputs
├── att_factors_*.csv           # Per-fund attribution data
├── reference.csv               # Security reference data
├── curves.csv                  # Yield curve data
├── schedule.csv                # Bond schedule data
├── holidays.csv                # Business day calendar
├── autogen_tickets.csv         # Automated exception tickets
├── cleared_exceptions.csv       # Ticket suppression list
├── data_issues.csv             # Issue tracking log
├── users.csv                   # User accounts for workflow
├── dashboard_kpis.json         # Dashboard cache (generated)
└── cache/                      # Attribution performance cache
    └── att_factors_*_cached.csv
```

### 4. Core Components & Logic

- `tools/run_all_checks.py`: Orchestrates staleness, max/min, file delivery, Z‑score metrics; writes `Data/dashboard_kpis.json`; generates exception tickets.
- `core/settings_loader.py`: Centralized settings loader/caching for `settings.yaml`.
- `data_processing/preprocessing.py` / `tools/run_preprocessing.py`: Normalize headers, coerce types, enrich metadata, write standardized CSVs, trigger synthetic analytics.
- `analytics/metric_calculator.py`: Compute summary metrics, z‑scores, and statistics.
- `tools/staleness_detection.py`: Flags long runs of placeholder or identical values (N consecutive business days).
- `analytics/maxmin_processing.py`: Threshold breaches across security‑level files.
- `analytics/file_delivery_processing.py`: Delivery completeness/health logging.
- `data_processing/price_matching_processing.py`: Compares delivered prices vs `sec_Price.csv`.
- `analytics/ticket_processing.py`: Automated exception ticket generation with deduplication and suppression.
- `analytics/issue_processing.py`: Manual issue tracking with Jira integration and comment timelines.
- `tools/populate_attribution_cache.py`: Pre-computes attribution aggregates for performance optimization.
- `analytics/security_data_provider.py`: **NEW** - Unified data layer for consistent security data access across all calculators.
- `views/*`: Route handlers rendering pages and JSON APIs.

Related analytics (SpreadOMatic): 
- `analytics/synth_spread_calculator.py` - Synthetic spread calculations with SecurityDataProvider
- `analytics/synth_analytics_csv_processor.py` - Comprehensive analytics CSV generation
- `analytics/security_data_provider.py` - Unified data layer for consistent security data access across all calculators

### 5. Data Flow (text diagram)

```
(Input CSVs)      (Processing)                          (Cache/Output)                 (Presentation)
Data/*.csv  -->  run_preprocessing.py  -->  normalized sec_/ts_ files  -->  run_all_checks.py  -->  Data/dashboard_kpis.json  -->  Flask UI
                       ^                                |                                     ^
                       |                                v                                     |
                   settings.yaml  <--------------  settings_loader.py  ------------------------+
```

### 6. How to Execute Key Tasks

```powershell
# Run the web application
python app.py

# Run the entire suite of checks and refresh dashboard cache
python tools/run_all_checks.py

# Run individual checks
python tools/staleness_detection.py
python analytics/maxmin_processing.py
python analytics/file_delivery_processing.py

# Preprocess inputs after API fetches or file drops
python tools/run_preprocessing.py
```

### 7. Links to Detailed Docs

- For exhaustive user documentation and data schemas, see [Complete User Documentation](./clean_encyclopedia.md).
- For the auto‑generated combined docs snapshot used previously, see `OLD_docs/combined_documentation.md` in this repository.
- SecurityDataProvider refactoring: See `OLD_docs/SecurityDataProvider_Refactoring_Complete.md` for implementation details.

---

## SecurityDataProvider Unified Data Layer

### Overview
Successfully implemented a unified SecurityDataProvider that eliminates data divergence between calculation methods. This critical refactoring ensures both `synth_spread_calculator.py` and `synth_analytics_csv_processor.py` use identical data sources and merging logic.

### Key Benefits Achieved

#### ✅ Eliminated Data Divergence
- Both SpreadOMatic and comprehensive CSV methods now use identical data
- Consistent ISIN normalization (including unicode dashes)
- Same priority logic for data merging

#### ✅ Single Source of Truth
- All data collection centralized in SecurityDataProvider
- Consistent fallback logic:
  - Accrued: sec_accrued → schedule → 0.0
  - Coupon: reference → schedule → 0.0
  - Currency: reference Position Currency → reference Currency → sec_Price Currency → USD
  - Maturity: reference → schedule → 5 years from valuation
  - Issue: reference → schedule → 1 year before valuation
  - DayCountConvention: reference → "30E/360" (default)
  - BusinessDayConvention: reference → "MF" (default)

#### ✅ Test-Driven Development
- **File**: `tests/test_security_data_provider.py` (28 tests, all passing)
- **Integration tests**: `tests/test_integration_unified_provider.py`
- **Comprehensive coverage**: ISIN normalization, data merging, fallback logic

### Implementation Details

#### 1. Created SecurityDataProvider (TDD Approach)
- **File**: `analytics/security_data_provider.py`
- **Purpose**: Single source of truth for security data collection and merging
- **Key Features**:
  - Unified ISIN normalization (handles hyphenated variants)
  - Priority-based data merging with consistent defaults
  - Automatic cache invalidation when source files change
  - Multi-level fallback logic for all security attributes

#### 2. Refactored synth_spread_calculator.py
- **Backup**: `synth_spread_calculator_original.py`
- **Changes**:
  - Replaced direct CSV reads with `provider.get_security_data()`
  - Removed duplicate normalization logic
  - Uses unified accrued lookup
  - Added logging: "REFACTORED VERSION: Using SecurityDataProvider"
  - Added business-day-adjusted schedule generation: Applies BusinessDayConvention from reference.csv to coupon and maturity dates using currency-specific holiday calendars

#### 3. Refactored synth_analytics_csv_processor.py
- **Backup**: `synth_analytics_csv_processor_original.py`
- **Changes**:
  - Replaced `load_supporting_data()` to use SecurityDataProvider
  - Removed `_combine_security_data()` function
  - Uses consistent defaults from provider
  - Simplified data access patterns
  - Added NextCall/Worst analytics for callable bonds (line 388): Computes yield/spread/risk metrics to next call and worst call dates for any callable instrument with a call schedule
  - Added coupon unit normalization for call analytics: Converts coupon percent→decimal for Next/Worst call computations to prevent unit drift
  - Added business-day-adjusted call-horizon cashflows: Passes BusinessDayConvention and currency to YTW utilities for accurate call analytics

#### 4. Data Consistency Guarantee
The SecurityDataProvider ensures both calculators use:
- Identical security reference data with proper ISIN normalization
- Same accrued interest values with multi-level fallback logic
- Consistent data priority merging (sec_accrued > reference > schedule)
- Automatic cache invalidation when source files change

### Technical Architecture

#### File Structure
```
analytics/
├── security_data_provider.py          # Unified data layer
├── synth_spread_calculator.py         # Refactored SpreadOMatic calculator
├── synth_analytics_csv_processor.py   # Refactored comprehensive processor
├── synth_spread_calculator_original.py # Backup of original implementation
└── synth_analytics_csv_processor_original.py # Backup of original implementation

tests/
├── test_security_data_provider.py     # 28 comprehensive tests
└── test_integration_unified_provider.py # Integration validation tests
```

#### Core Methods
```python
class SecurityDataProvider:
    def get_security_data(self, isins: List[str]) -> pd.DataFrame:
        """Get unified security data for given ISINs with consistent fallbacks"""
        
    def get_single_security_data(self, isin: str) -> Dict[str, Any]:
        """Get complete data for single security with all attributes"""
        
    def _normalize_isin(self, isin: str) -> str:
        """Normalize ISIN handling hyphenated variants"""
```

### Usage Impact

#### Before Refactoring
Two different calculation methods could produce different results due to:
- Inconsistent ISIN normalization
- Different data merging priorities  
- Separate fallback logic implementations
- Manual data loading patterns

#### After Refactoring
Both calculation methods now guarantee:
- Identical security data for same ISIN
- Consistent handling of edge cases
- Same fallback values when data is missing
- Single point of control for data access logic

### Validation Results
- **SecurityDataProvider Tests**: PASS (28/28)
- **Calculation Comparison**: PASS (Identical outputs verified)
- **Data Consistency**: PASS (No divergence detected)
- **Integration Tests**: PASS (Full workflow validation)

---

### 8. Recent Changes and Versioning (highlights)

#### Major Architectural Improvements
- **SecurityDataProvider Refactoring**: Unified data layer eliminating calculation divergence
  - Both `synth_spread_calculator.py` and `synth_analytics_csv_processor.py` now use identical data
  - TDD approach with 28 comprehensive tests in `tests/test_security_data_provider.py`
  - Integration tests validating consistent calculations across methods
  - Consistent ISIN normalization and multi-level fallback logic

#### Analytics & Debug Workstation Enhancements  
- **Enhanced Analytics Debug Workstation**: Refactored to modular 7-panel architecture
  - Component-based templates for better maintainability
  - Modular JavaScript controllers with clear separation of concerns
  - Smart diagnostics with AI-powered root cause analysis
  - Enhanced analytics support (G-Spread, YTW, Key Rate Durations)

#### Development Standards & Quality
- **Comprehensive Type Hinting**: All functions throughout codebase now have proper type annotations
  - Improved IDE support and code maintainability  
  - mypy compatibility for static type checking
  - Standard typing patterns across all modules
- **Test-Driven Development**: Extensive test coverage for critical components
  - Fixed-income analytics harness validates YTM, spreads, duration, convexity
  - Goal seek convergence tests with comprehensive edge case coverage

#### Data Processing Robustness
- Enhanced robustness in data processing (MultiIndex concat, `.dt` accessor fixes)  
- Automatic post‑ingestion workflow: preprocessing → quality checks → dashboard cache
- Security summary caching and performance improvements across views
- Navigation and naming fixes; centralized logic and metric config mapping

### 9. Extension Points (Configuration‑First)

- YAML as source of truth: all configuration centralized in `settings.yaml`
- Dynamic loader patterns in `core/data_loader.py`/helpers avoid hard‑coded column names
- Add new metrics by extending `metric_file_map` section in `settings.yaml` (ts/sp_ts/sec/sec_sp) and reusing generic views
- Ticket system: create via `ticket_processing.create_ticket(...)`; suppression uses canonicalization + hashing
- UI: componentized Jinja templates; navigation via `navigation_config.py`
- Scheduling: background/threaded runs; extensible for job management
- CSV Export: Automatic export buttons for all tables via `static/js/modules/utils/csvExport.js`
- Attribution caching: Pre-computed daily aggregates in `Data/cache/` for performance

### 10. Ticket & Issue Workflow

- **Automated Ticket Generation**: Data quality checks automatically create tickets for exceptions
- **Ticket Lifecycle**: Unallocated → Assigned → Clear/Retest → Suppression/Issue
- **Issue Management**: 
  - Optional escalation from tickets to issues
  - Comment timelines and status tracking
  - Jira integration for external tracking
- **Audit Trail**: Full history preserved from detection to remediation
- **Suppression System**: Canonical hashing prevents duplicate tickets

### 11. Practical Risks and Mitigations

- Date handling ambiguity → maintain/extend `date_patterns.yaml`
- Data volume/memory → consider chunked loaders or Dask for very large datasets
- Concurrency → prefer stateless handlers, idempotent batch jobs; CSV locks via `filelock`
- Attribution file size → use caching system with pre-computed aggregates
- Performance bottlenecks → monitor via `instance/loading_times.log`

### 12. Testing, Typing, and Linting

#### **Comprehensive Test Coverage Implementation**

**Test Suite Status**: ✅ **242 total tests** (207 structural + 35 real execution) with **97% pass rate** (execution time: ~4.5 seconds)

**Coverage Achievement**:
- **Baseline**: 34% coverage
- **Foundation & Stabilization**: +4-6% (stabilized failing tests + core helper coverage)
- **Core Analytics & Data Processing**: +10-14% (analytics module comprehensive testing)
- **Bond Calculations & Unified Data**: +8-12% (mathematical invariants + data layer testing)
- **Data Processing & API Validation**: +6-10% (preprocessing + API logic testing)
- **Real Code Execution**: Measured coverage with actual business logic execution
- **Final Measured**: 10% overall (87% SecurityDataProvider, 41% core/utils) with real execution validation

**Phase 0 - Foundation & Stabilization**:
- ✅ **Fixed 3 failing tests**: `test_bond_calculation_excel.py`, `test_integration_unified_provider.py`, `test_synth_alignment.py`
- ✅ **Enhanced test infrastructure**: `conftest.py` with `mini_dataset`, `app_config`, `freeze_time` fixtures
- ✅ **Core utilities coverage**: `tests/test_core_utils_phase0.py` (20 tests) - date patterns, fund parsing, NaN handling, YAML loading, business days
- ✅ **SecurityDataProvider testing**: `tests/test_security_data_provider_phase0.py` (11 tests) - ISIN normalization, currency precedence, data merging
- ✅ **Flask import isolation**: Fixed conditional imports to allow tests without Flask dependencies

**Phase 1 - Core Analytics & Data Processing**:
- ✅ **Statistical analytics**: `tests/test_metric_calculator_phase1.py` (25 tests) - Z-scores, MultiIndex handling, relative metrics, sorting
- ✅ **Threshold monitoring**: `tests/test_maxmin_basic.py` (8 tests) - breach detection, distressed exclusions, NaN handling
- ✅ **Issue management**: `tests/test_issue_processing_simple.py` (16 tests) - lifecycle management, comment serialization, ID generation
- ✅ **Data quality checks**: Comprehensive edge case testing and error handling across all modules

**Bond Calculations & Unified Data**:
- ✅ **SecurityDataProvider enhancements**: `tests/test_security_data_provider_phase2.py` (20 tests) - ISIN normalization, currency precedence, accrued interest priority, cache invalidation
- ✅ **Bond analytics invariants**: `tests/test_bond_analytics_invariants.py` (14 tests) - YTM monotonicity, duration relationships, convexity validation, spread sign conventions
- ✅ **Synthetic analytics integration**: `tests/test_synthetic_analytics_basic.py` (12 tests) - term parsing, zero curve construction, end-to-end data flow

**Data Processing & API Validation**:
- ✅ **Preprocessing pipeline**: `tests/test_preprocessing_simple.py` (18 tests) - date reading/sorting, header replacement, ISIN suffixing, metadata detection
- ✅ **Data validation framework**: `tests/test_data_validation_phase3.py` (30 tests) - structure validation, file-type specific logic, error handling
- ✅ **API logic validation**: `tests/test_api_logic_only.py` (20 tests) - request/response structures, security validation, parameter ranges
- ✅ **Bond API robustness**: `tests/test_bond_api_robust.py` (10 tests) - calculation logic, mocking strategies, environment independence

**Real Code Execution & SpreadOMatic Integration**:
- ✅ **Core utilities real execution**: `tests/real_execution/test_core_utils_real.py` (20 tests) - actual string parsing, date operations, YAML loading, business day calculations
- ✅ **SecurityDataProvider real operations**: `tests/real_execution/test_security_data_provider_real.py` (15 tests) - actual CSV loading, DataFrame merging, ISIN normalization, cache invalidation
- ✅ **SpreadOMatic financial calculations**: `tests/real_execution/test_spreadomatic_real.py` (12 tests) - real YTM solving, spread calculations, duration/convexity computation

**Test Design Excellence**:
- ✅ **Dual testing strategy**: Structural tests (mocked) + real execution tests (unmocked) for comprehensive validation
- ✅ **Synthetic data fixtures**: No dependency on real `Data/` folder for reliability
- ✅ **Fast execution**: Structural tests <50ms each, real execution tests <100ms each, total suite <4.5 seconds
- ✅ **Deterministic results**: Reproducible outcomes using controlled test data
- ✅ **Production-ready**: Comprehensive error handling and edge case coverage
- ✅ **Mathematical validation**: Bond analytics invariants and financial relationships tested with real SpreadOMatic functions
- ✅ **Integration testing**: End-to-end workflows with SecurityDataProvider unified data layer
- ✅ **Environment independence**: Tests work in command line, GUI, and CI/CD environments
- ✅ **API validation**: Request/response structures and security patterns tested without Flask dependencies
- ✅ **Real code coverage**: Actual business logic execution measured with meaningful coverage metrics

**Legacy Testing Infrastructure**:
- Type hints across modules (see `OLD_docs/TYPE_HINTS_SUMMARY.md`)
- Linting via Flake8 (`.flake8` config)
- Fixed-income analytics harness: `tests/test_fixed_income_harness.py` validates YTM, spreads, duration, convexity
- Goal seek convergence tests: Binary search optimization with comprehensive edge case coverage

#### Development Standards & Type Hints

**Comprehensive Type Hinting**: All functions throughout the application now have proper type annotations following Python's type hinting standards using the `typing` module.

**Files with Complete Type Hints**:
- Core application files: `app.py`, `utils.py` 
- Data processing: `metric_calculator.py`, `data_loader.py`, `data_validation.py`, `data_utils.py`
- Processing modules: `run_all_checks.py`, `staleness_detection.py`, `ticket_processing.py`, `preprocessing.py`
- Views: `main_views.py`, `security_views.py` and other view modules
- Analytics: All modules in `analytics/` directory

**Type Hint Patterns Applied**:
```python
# Function parameters and return types
def function_name(param1: str, param2: int, optional_param: Optional[str] = None) -> ReturnType:

# Complex return types  
def get_data() -> Dict[str, Any]:
def process_file() -> Optional[pd.DataFrame]:
def validate() -> Tuple[bool, List[str]]:

# Data processing types
Dict[str, Any]        # Configuration dictionaries
List[str]             # Lists of strings  
Optional[T]           # Nullable types
Tuple[A, B, C]        # Multi-return functions
pd.DataFrame          # DataFrame operations
Optional[pd.DataFrame] # Nullable DataFrames
```

**Import Standards**:
```python
from typing import List, Dict, Any, Optional, Union, Tuple, TYPE_CHECKING
```

**Comprehensive Updates Completed:**

**Core Application Files:**
- `app.py`: Functions updated include `prune_old_logs()`, `create_app()`, `favicon()`, `inject_nav_menu()`
- `utils.py`: Comprehensive typing for all utility functions including file operations, data processing, and configuration handling

**Data Processing Files:**
- `metric_calculator.py`: Already had comprehensive type hints
- `data_loader.py`: Already had comprehensive type hints
- `data_validation.py`: Already had comprehensive type hints
- `data_utils.py`: Already had comprehensive type hints
- **NEW** `analytics/security_data_provider.py`: Full type hints with dataclasses

**Processing Modules:**
- `run_all_checks.py`: All functions now have proper parameter and return type annotations
- `staleness_detection.py`: Comprehensive typing for data analysis functions
- `ticket_processing.py`: Already had comprehensive type hints
- `preprocessing.py`: Already had comprehensive type hints
- `synth_spread_calculator.py`: Refactored with SecurityDataProvider integration
- `synth_analytics_csv_processor.py`: Refactored with SecurityDataProvider integration

**View Files:**
- `views/main_views.py`: All route handlers and helper functions
- `views/security_views.py`: Large file with extensive security data processing functions

**Type Hint Standards Applied:**
1. **Function Parameters**: All functions have typed parameters
   ```python
   def function_name(param1: str, param2: int, optional_param: Optional[str] = None) -> ReturnType:
   ```

2. **Return Types**: All functions have explicit return type annotations
   ```python
   def get_data() -> Dict[str, Any]:
   def process_file() -> Optional[pd.DataFrame]:
   def validate() -> Tuple[bool, List[str]]:
   ```

3. **Complex Types**: Proper use of generic types
   ```python
   Dict[str, Any]  # For configuration dictionaries
   List[str]       # For lists of strings
   Optional[T]     # For nullable types
   Tuple[A, B, C]  # For multi-return functions
   ```

**Benefits**:
- Enhanced IDE support with autocomplete and error detection
- Improved code maintainability and documentation
- Better developer experience and easier onboarding
- Static type checking compatibility with mypy

### 13. Bond Calculator & Analytics Tools

- **Bond Calculator**: Web-based calculator at `/bond/calculator` providing:
  - YTM, Z-Spread, G-Spread, Effective/Modified Duration, Convexity
  - Key-Rate Durations, cashflow analysis, interactive charts
  - API endpoints:
    - `POST /bond/api/calc` - Calculate bond analytics
    - `GET /bond/api/lookup` - Lookup bond details by ISIN
    - `GET /bond/api/price` - Get price for ISIN and date
    - `POST /bond/api/excel` - Generate Excel workbook
  - Uses SpreadOMatic engine for analytics calculations
  - Goal seek functionality with binary search optimization

- **Analytics Debug Workstation**: Advanced bond analytics debugging at `/bond/debug`
  - **Modular Architecture**: 7-panel design with component-based templates
  - **Smart Diagnostics**: AI-powered root cause analysis with confidence scoring
  - **Real-time Sensitivity**: Live parameter adjustment with immediate recalculation
  - **Enhanced Analytics**: G-Spread, YTW, Key Rate Durations, and OAS calculations
  - **Goal Seek & Scenarios**: Advanced scenario modeling with vendor matching
  - **Modular Components**: Separate template components for maintainability
    - `_header.html`, `_security_setup.html`, `_smart_diagnostics.html`
    - `_sensitivity_analysis.html`, `_goal_seek.html`, `_data_inspector.html`
    - `_advanced_tools.html` - Each panel independently maintainable
  - **JavaScript Architecture**: Modular controller classes in `static/js/modules/analytics/`
    - `debugWorkstation.js` - Main coordinator
    - `securitySearch.js` - Security selection
    - `smartDiagnostics.js` - Automated diagnostics
    - `dataInspector.js` - Raw data inspection

### 14. UI Design System

- **Color Palette**: Semantic colors defined in `tailwind.config.js`
  - Primary (#E34A33), Secondary (#1F7A8C), Success (#10B981)
  - Warning (#F59E0B), Danger (#EF4444), Info (#3B82F6)
- **Component Standards**: 
  - No emojis in financial interfaces
  - Professional minimal styling with high contrast
  - Consistent button patterns for actions and diagnostics
- **Dashboard Features**:
  - KPI tiles with responsive grid layout
  - Fund health table with per-metric Z-scores
  - RAG status indicators (Red/Amber/Green)
  - Last data refresh indicator with staleness warnings
  - Client-side sortable tables with custom severity ordering

### 15. Developer Commands (PowerShell)

```powershell
# Run app
python app.py

# Run all checks
python tools/run_all_checks.py

# Selected checks
python tools/staleness_detection.py
python analytics/maxmin_processing.py
python analytics/file_delivery_processing.py

# Preprocessing
python tools/run_preprocessing.py

# Attribution cache population
python tools/populate_attribution_cache.py
python tools/populate_attribution_cache.py --fund IG01 --force

# Tests & lint
pytest -q
pytest --cov  # with coverage
pytest tests/test_fixed_income_harness.py  # bond analytics tests
flake8
```

### 16. Developer Tools

#### Markdown Combiner

A Python script that combines all markdown files in a workspace into a single comprehensive document. Located at `tools/markdown_combiner.py`.

**Features:**
- 🔍 **Automatic Discovery**: Finds all markdown files (`.md`, `.mdc`, `.markdown`, `.mkd`) in the workspace
- 📁 **Smart Filtering**: Excludes common directories like `node_modules`, `.git`, `.vscode`, etc.
- 📝 **Organized Output**: Creates a well-structured document with header, table of contents, and individual sections
- 🛠️ **Flexible Options**: Configurable output file, directory exclusions, and verbosity
- 🔧 **Error Handling**: Robust file reading with encoding fallback

**Basic Usage:**
```powershell
python tools/markdown_combiner.py
```

**Advanced Usage:**
```powershell
# Custom output file
python tools/markdown_combiner.py --output my_docs.md

# Verbose output showing file details
python tools/markdown_combiner.py --verbose

# Include all directories (don't exclude node_modules, etc.)
python tools/markdown_combiner.py --include-all

# Exclude additional directories
python tools/markdown_combiner.py --exclude-dirs temp logs cache

# Search from specific root directory
python tools/markdown_combiner.py --root ./docs
```

**Command Line Options:**
- `--output` / `-o`: Output file name (default: `combined_documentation.md`)
- `--root` / `-r`: Root directory to search (default: current directory)
- `--verbose` / `-v`: Show detailed output including file sizes
- `--include-all`: Include all directories (don't exclude common ones)
- `--exclude-dirs`: Additional directories to exclude (space-separated)

### 17. Module Documentation

#### Python Core Modules

**Data Processing Core:**
- `app.py`: Flask app factory and routing bootstrap
- `core/data_loader.py`: Core data loading and processing
- `data_processing/preprocessing.py`: Raw data standardization and cleanup
- `data_processing/data_validation.py`: Structure and content validation
- `core/data_utils.py`: Utility functions for data processing
- `data_processing/data_audit.py`: Data consistency auditing
- `analytics/metric_calculator.py`: Summary metrics and z-scores
- `analytics/security_processing.py`: Security-level data processing

**Analysis & Processing Modules:**
- `data_processing/curve_processing.py`: Yield curve analysis
- `analytics/issue_processing.py`: Issue tracking and management
- `tools/staleness_detection.py`: Stale data detection
- `analytics/staleness_processing.py`: Staleness processing and reporting
- `analytics/maxmin_processing.py`: Threshold breach detection
- `analytics/file_delivery_processing.py`: File delivery monitoring

**Configuration & Utilities:**
- `core/config.py`: Configuration constants
- `core/navigation_config.py`: UI navigation structure
- `core/utils.py`: General utility functions
- `tools/run_preprocessing.py`: Batch preprocessing script
- `tools/create_shortcuts.py`: Desktop shortcut creation
- `tools/setup_installer.py`: Application installer

#### Views Structure

**Core Application Views:**
- `main_views.py`: Dashboard and main pages
- `metric_views.py`: Metric analysis pages
- `security_views.py`: Security detail pages
- `fund_views.py`: Fund analysis pages
- `curve_views.py`: Yield curve analysis
- `issue_views.py`: Issue management

**Dashboard & Analysis Views:**
- `maxmin_views.py`: Threshold breach dashboard
- `staleness_views.py`: Staleness analysis
- `file_delivery_views.py`: File delivery monitoring
- `watchlist_views.py`: Watchlist management
- `exclusion_views.py`: Exclusion management
- `weight_views.py`: Weight analysis
- `inspect_views.py`: Data inspection tools

**Attribution & Comparison Views:**
- `attribution_views.py`: Attribution analysis
- `attribution_processing.py`: Attribution data processing
- `generic_comparison_views.py`: Generic comparison engine
- `comparison_helpers.py`: Comparison utilities
- `security_helpers.py`: Security data helpers

**API Infrastructure:**
- `api_views.py`: Main API routes
- `api_core.py`: Core API functionality
- `api_routes_data.py`: Data API routes
- `api_routes_call.py`: Call API routes

#### Templates Structure

The application uses Jinja2 templates organized by functionality:
- Base & Dashboard Templates: `base.html`, `index.html`, `dashboard.html`
- Data & Security Pages: `get_data.html`, `securities_page.html`, `security_details_page.html`
- Fund & Analysis Pages: `fund_detail_page.html`, `fund_duration_details.html`
- Curve Analysis Templates: `curve_summary.html`, `curve_details.html`
- Attribution Templates: `attribution_summary.html`, `attribution_charts.html`
- Comparison Templates: `comparison_summary_base.html`, `comparison_details_base.html`

#### Static Files Structure
- `static/js/main.js`: Main JavaScript functionality
- `static/js/modules/`: Modular JavaScript components
- `static/css/`: Tailwind CSS and custom styles

### 18. Analytics Generation - Comprehensive CSV

The system generates comprehensive analytics CSV files through the SpreadOMatic tool integration. This functionality provides institutional-grade bond analytics in a standardized CSV format.

#### File Generation Process
1. **Data Collection**: Gathers bond static data, market prices, yield curves, and call schedules
2. **Analytics Calculation**: Computes spreads (ASW, Z-spread, OAS), durations (modified, effective, spread), convexity, DV01
3. **Output Structure**: Creates standardized CSV with 50+ analytics columns per bond

#### Key Analytics Columns
**Pricing Metrics:**
- Clean/dirty prices
- Accrued interest
- YTM (Yield to Maturity)
- YTW (Yield to Worst)

**Spread Analytics:**
- ASW (Asset Swap Spread)
- Z-spread (Zero-volatility spread)
- G-spread (Government spread)
- I-spread (Interpolated spread)
- OAS (Option-Adjusted Spread)

**Risk Measures:**
- Modified duration
- Effective duration
- Spread duration
- Convexity
- DV01 (Dollar value of 01)

**FRN Analytics:**
- Discount Margin (bps): Constant add-on to floating coupons that matches PV to market price

**Option Greeks (for callable bonds):**
- Delta: Price sensitivity to underlying
- Gamma: Rate of change of delta
- Vega: Volatility sensitivity
- Theta: Time decay

**Attribution Components:**
- Carry component
- Roll-down effect
- Curve movement
- Spread changes

#### Implementation Details

```python
# From synth_analytics_csv_processor.py
analytics_columns = [
    'ISIN', 'SecurityName', 'Currency', 'MaturityDate',
    'CleanPrice', 'DirtyPrice', 'YTM', 'YTW',
    'ModifiedDuration', 'EffectiveDuration', 'SpreadDuration',
    'Convexity', 'DV01', 'ASWSpread', 'ZSpread', 'OAS',
    'Discount_Margin_bps', 'Delta', 'Gamma', 'Vega', 'Theta'
]

# Performance metrics
Processing Time: ~0.5-1.0 seconds per bond
Memory Usage: ~100MB for 1000 bonds
Output Size: ~500KB CSV for 100 bonds with full analytics
```

#### Data Flow
```
Bond Data + Market Data → SpreadOMatic Engine → Analytics Calculation → CSV Export
                              ↓
                    Hull-White Model (for OAS)
                              ↓
                    Monte Carlo Simulation
```

#### Usage Example
```python
from analytics.synth_analytics_csv_processor import generate_comprehensive_csv

# Generate analytics for portfolio
analytics_df = generate_comprehensive_csv(
    bond_data=bond_df,
    market_data=market_df,
    curve_date=datetime(2024, 1, 15),
    output_path='Data/comprehensive_analytics.csv'

)
```

### SpreadOMatic Yield Spread Functions

The `tools/SpreadOMatic/spreadomatic/yield_spread.py` module provides core bond analytics functions for solving spreads and margins.

#### discount_margin() Function

Solves the discount margin for Floating Rate Notes (FRNs) using a closed-form analytical approach.

**Signature:**
```python
def discount_margin(
    price: float,
    payment_schedule: List[dict],
    valuation_date,
    proj_zero_times: List[float],
    proj_zero_rates: List[float],
    disc_zero_times: List[float],
    disc_zero_rates: List[float],
    day_basis: str,
    *,
    comp: Compounding = "annual",
) -> float
```

**Algorithm:**
1. Projects floating coupons using the projection curve (forwards)
2. Computes base PV using discount curve
3. Calculates PV weight of 1.0 margin across floating coupons: Σ(DF_i × accr_i × notional_i)
4. Solves closed-form: dm = (price - PV_base) / PV_weight

**Key Features:**
- Analytical solution (no iteration required)
- Separates projection curve (for coupon forwards) from discount curve (for PV)
- Linear in margin allows closed-form solving
- Raises clear error for non-FRN schedules

**Usage in Synthetic Analytics:**
Integrated into `synth_analytics_csv_processor.py` for comprehensive FRN analytics. Uses heuristic FRN detection based on security name/type containing "FRN", "FLOAT", or "FLT".

### Attribution Cache Implementation

The `AttributionCache` class in `views/attribution_cache.py` provides a high-performance caching layer for attribution aggregates, essential for handling large (~100MB) attribution files.

#### Architecture
```python
class AttributionCache:
    def __init__(self, data_folder: str)
    def compute_daily_aggregates(self, df: pd.DataFrame, fund: str) -> Dict[str, pd.DataFrame]
    def save_cache(self, fund: str, aggregates: Dict[str, pd.DataFrame])
    def load_cache(self, fund: str, cache_type: str) -> Optional[pd.DataFrame]
    def get_aggregates_with_cache(self, fund: str, level: str, ...) -> pd.DataFrame
    def refresh_cache(self, fund: str)
    def clear_cache(self, fund: Optional[str] = None)
```

#### Key Implementation Details

**Cache Validation Logic:**
```python
def _is_cache_valid(self, cache_file: str, source_mtime: float) -> bool:
    if not os.path.exists(cache_file):
        return False
    cache_mtime = os.path.getmtime(cache_file)
    return cache_mtime >= source_mtime  # Cache must be newer than source
```

**Multi-Level Aggregation:**
- **L0**: Daily residuals, absolute residuals, returns, and total attribution
- **L1**: Factor group aggregates (Rates, Credit, FX) plus returns/residuals
- **L2**: All detailed factor aggregates plus returns/residuals

**Performance Optimization:**
- Caches computed aggregates as CSV files with `_cached` suffix
- Cache location: `Data/cache/` directory
- Automatic cache invalidation on source file modification
- Integrated timing logs for monitoring (compatible with `loading_times.log`)

**Timing Integration:**
```python
def _log_timing(self, operation: str, duration_ms: float, details: str = ""):
    msg = f"OPERATION:attribution_cache | ACTION:{operation} | DURATION:{duration_ms:.2f}ms"
    if details:
        msg += f" | DETAILS:{details}"
    self.timing_logger.info(msg)
```

#### Cache Operations

**Get Aggregates with Smart Caching:**
1. Check if valid cache exists
2. If cache hit: Load and apply filters
3. If cache miss: Load source, compute all levels, save cache
4. Return filtered results

**Refresh Strategy:**
- Automatic: Cache invalidated when source file is newer
- Manual: `refresh_cache()` forces recomputation
- Clear: `clear_cache()` removes cache files

#### Performance Metrics
- Typical cache hit: <500ms for 100MB files
- Cache computation: 30-60 seconds (one-time)
- Cache size: ~10-20% of original file
- Operations logged with millisecond precision

#### Integration Points
- Used by `views/attribution_processing.py` for UI rendering
- Called by `populate_attribution_cache.py` for batch processing
- Timing logs integrate with system monitoring

- `static/img/`: Images and icons
