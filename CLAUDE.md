
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Simple Data Checker is a comprehensive Flask-based web application for financial data validation and analysis, specifically designed for fixed income analytics. It ingests, validates, and analyzes time-series and security-level data including spreads, duration, YTM/YTW, and attribution factors.

## Documentation Structure

The project maintains three primary documentation files in the `CleanDocs/` directory that should be kept up-to-date:

### Clean Documentation Files
- **`clean_encyclopedia.md`** - Comprehensive user documentation covering all features, workflows, and usage instructions. Update this when adding new user-facing features or changing existing functionality.
- **`clean_TECHNICAL_OVERVIEW.md`** - Technical documentation for developers including architecture, implementation details, and system design. Update this when adding new technical components or changing architectural patterns.
- **`clean_readme.md`** - Quick start guide and project overview. Update this for installation changes or major feature additions.

When making significant code changes:
1. Update the appropriate Clean_ documentation file(s)
2. Remove outdated information from OLD_docs/ if superseded
3. Keep documentation factual without temporal markers (avoid "NEW", dates, version numbers)

## Specialized Tools

### Analytics Tools
- **SpreadOMatic** (`tools/SpreadOMatic/`) - Advanced bond analytics calculation engine
  - OAS calculation with Hull-White model
  - Z-Spread calculations
  - Key rate duration calculations
  - Cashflow generation and yield calculations
  - Settlement-aware analytics

### Testing Tools
- **Real Execution Tests** (`tests/real_execution/`) - Tests with actual data and calculations
- **Phase-based Testing** - Progressive test suites (phase0, phase1, phase2, etc.)

### Data Generation
- **Synthetic Analytics Generator** (`analytics/synth_analytics_csv_processor.py`) - Creates synthetic security analytics
- **Hull-White Market Data Generator** (`tools/generate_hull_white_market_data.py`) - Generates test market data

## Key Commands

### Application Management
```bash
# Start the application (Windows)
run_app.bat

# Start development server manually
python app.py

# Run all data quality checks
python run_all_checks.py

# Run data preprocessing
python run_preprocessing.py
```

### Testing and Quality
```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov --cov-report=html

# Run specific test modules
pytest tests/test_data_loader.py

# Run tests matching a pattern
pytest -k "test_security"

# Run tests excluding slow/external tests  
pytest -m "not slow and not e2e"

# Run only fast unit tests
pytest -m "not slow"

# Lint Python code
flake8

# Build CSS (requires Node.js)
npm run build:css
```

### Data Processing
```bash
# Process raw data files
python run_preprocessing.py

# Run comprehensive data quality checks (includes ticket generation)
python run_all_checks.py

# Populate attribution cache
python populate_attribution_cache.py
```

## High-Level Architecture

### Application Structure
- **Flask Application Factory Pattern**: Modular app creation using `create_app()` in `app.py`
- **Blueprint-based Architecture**: Routes organized across multiple blueprints in `views/` directory
- **Configuration-Driven Design**: Extensive use of YAML configuration files for feature settings
- **CSV-based Data Storage**: Transparent, auditable data persistence using standardized CSV formats

### Core Data Flow
1. **Raw Data Ingestion**: Files preprocessed via `preprocessing.py` and `run_preprocessing.py`
2. **Data Loading**: Feature-specific modules (`data_loader.py`, `security_processing.py`, `curve_processing.py`)
3. **Validation & Auditing**: Real-time validation via `data_validation.py` and on-demand audits via `data_audit.py`
4. **Analysis & Metrics**: Specialized modules for calculations, Z-scores, staleness detection, and comparisons
5. **UI Rendering**: Jinja2 templates with Tailwind CSS styling and JavaScript modules

### Key Components

#### Data Processing Pipeline
- **Preprocessing**: `preprocessing.py` - Standardizes file formats, normalizes headers, handles vendor-specific formats
- **Loading**: `data_loader.py` - Flexible, defensive loading with dynamic column identification
- **Validation**: `data_validation.py`, `data_audit.py` - Comprehensive data integrity checks

#### Analysis Modules
- **Metrics**: `metric_calculator.py` - Time-series metrics with Z-score outlier detection
- **Security Analysis**: `security_processing.py` - Security-level metrics with volatility screening
- **Staleness Detection**: `staleness_processing.py` - Configurable stale data identification
- **Threshold Monitoring**: `maxmin_processing.py` - Min/max threshold breach detection

#### Workflow Management
- **Ticket System**: `ticket_processing.py` - Automated exception ticketing with smart aggregation
- **Issue Tracking**: `issue_processing.py` - Manual issue management with Jira integration
- **Watchlist**: Audit-trail-enabled security monitoring

#### Views and UI
- **Blueprint Organization**: Each functional area has dedicated blueprints (`views/`)
- **Generic Comparison Engine**: YAML-configured comparison framework for any data pair
- **Navigation**: Centrally defined in `navigation_config.py`

### Configuration System

All major features are controlled via YAML configuration:
- `settings.yaml` - Main application settings
- `config/` directory - Feature-specific configurations
- Settings UI at `/settings` for runtime configuration management

## Development Guidelines

### Code Standards
- **Type Hints**: Use type annotations for all functions
- **Flask Blueprints**: Organize routes using blueprints for modularity
- **Application Factory Pattern**: Use `create_app()` for Flask initialization
- **Logging**: Use module-level loggers (`logging.getLogger(__name__)`)
- **Error Handling**: Defensive programming with comprehensive exception handling
- **PEP Compliance**: Follow PEP 8 and other relevant PEP standards
- **Module Design**: Follow SOLID principles and maintain clear module boundaries

### Data Processing Patterns
- **Dynamic Column Detection**: Use regex patterns instead of hard-coded column names
- **Zero Handling**: Always convert zeros to NaN to prevent false correlations
- **Date Parsing**: Flexible date handling supporting multiple formats
- **Caching**: Implement caching for expensive operations (security data loading)

### Testing Strategy
- **pytest**: Primary testing framework with configuration in `pytest.ini`
- **Coverage**: Use `pytest-cov` for coverage reporting
- **Test Markers**: Use markers for test categorization:
  - `slow`: Long-running or external-data tests
  - `e2e`: End-to-end tests requiring app running
- **Fixtures**: Proper test isolation with consistent fixtures in `conftest.py`
- **Module Testing**: Test data loading, parsing, calculations, and workflows

### Code Quality Tools
- **Flake8**: Configured in `.flake8` with:
  - Max line length: 88 (Black-compatible)
  - Complexity threshold: 10
  - Per-file ignores for test and config files
- **Black**: Code formatter (optional, line length 88)

### Frontend Development
- **Tailwind CSS**: Primary styling framework
- **Modular JavaScript**: Organize JS in `static/js/modules/` with clear separation of concerns:
  - `api/` - API service modules
  - `charts/` - Chart rendering modules  
  - `ui/` - UI component modules
  - `utils/` - Utility functions
- **Chart.js**: Standard charting library with encapsulated chart components
- **Progressive Enhancement**: Ensure base functionality without JavaScript
- **ES Modules**: Use ES6 modules with proper imports/exports
- **Event Delegation**: Use event delegation patterns for dynamic content

## Important File Locations

### Project Structure (Reorganized)
The codebase has been reorganized into a modular structure:

#### Core Modules (`core/`)
- `config.py` - Application constants and configuration loading
- `settings_loader.py` - Settings management from YAML files
- `navigation_config.py` - UI navigation structure
- `data_loader.py` - Main data loading utilities
- `data_utils.py` - CSV reading and data transformation utilities
- `io_lock.py` - File locking for concurrent CSV operations
- `utils.py` - Common utility functions

#### Data Processing (`data_processing/`)
- `data_validation.py` - Data validation routines
- `data_audit.py` - Data consistency auditing
- `preprocessing.py` - Data preprocessing pipeline
- `curve_processing.py` - Yield curve data processing
- `price_matching_processing.py` - Price comparison between sources

#### Analytics & Monitoring (`analytics/`)
- `metric_calculator.py` - Statistical metrics and Z-scores
- `security_processing.py` - Security-level analytics
- `staleness_processing.py` - Stale data detection
- `maxmin_processing.py` - Threshold breach detection
- `file_delivery_processing.py` - File delivery monitoring
- `issue_processing.py` - Issue tracking management
- `ticket_processing.py` - Automated ticket generation
- `synth_analytics_csv_processor.py` - Synthetic analytics generation
- `synth_spread_calculator.py` - SpreadOMatic calculations

#### Tools & Scripts (`tools/`)
- `run_preprocessing.py` - Batch preprocessing script
- `run_all_checks.py` - Data quality checks orchestrator
- `populate_attribution_cache.py` - Attribution cache population
- `staleness_detection.py` - Standalone staleness analysis
- `setup_installer.py` - Desktop application installer
- Other test and utility scripts

### Configuration
- `settings.yaml` - Main application settings
- `config/` - Feature-specific configuration files

### Views and Routes
- `views/` - All Flask blueprints and route handlers
- `templates/` - Jinja2 templates
- `static/` - CSS, JavaScript, and static assets

### Data Storage
- `Data/` - Main data directory (configurable)
- CSV files with standardized naming: `ts_*.csv`, `sec_*.csv`, `w_*.csv`

## Common Development Tasks

### Adding New Metrics
1. Add metric configuration to `config/metric_file_map.yaml`
2. Ensure data files follow naming convention (`ts_<metric>.csv`, `sec_<metric>.csv`)
3. Generic comparison and detail pages will automatically work

### Adding Data Quality Checks
1. Create new check module following existing patterns
2. Integrate with `run_all_checks.py`
3. Add ticket generation using `ticket_processing.create_ticket()`

### Extending UI
1. Create new blueprint in `views/`
2. Add templates following existing patterns
3. Update `navigation_config.py` for menu integration
4. Use Tailwind CSS classes for consistent styling

### Configuration Changes
1. Update relevant YAML files in `config/` or `settings.yaml`
2. Many settings reload automatically; some may require restart
3. Use `/settings` UI for runtime configuration management

## Architecture Patterns to Follow

### Modular Design
- Keep modules focused on single responsibilities
- Use dependency injection patterns
- Avoid circular imports
- Follow Flask blueprint patterns

### Configuration-First Development
- Make features configurable via YAML where possible
- Use generic engines that read configuration
- Avoid hard-coding business logic

### Defensive Programming
- Always handle missing data gracefully
- Log all critical operations
- Return structured errors for UI consumption
- Use comprehensive input validation

### Performance Considerations
- Implement caching for expensive operations
- Use pandas efficiently (avoid loops where possible)
- Consider memory usage for large datasets
- Log performance metrics for critical paths

## Security and Data Handling

### Data Privacy
- Never log sensitive business data
- Use ISINs and codes for identification in logs
- Store only metadata in monitoring logs
- Implement proper access controls

### Error Handling
- Log errors with context but not sensitive data
- Provide user-friendly error messages
- Implement proper exception handling chains
- Use structured error responses

## Deployment Notes

### Dependencies
- **Python**: Flask-based application with conda/pip dependencies
- **Node.js**: Required only for Tailwind CSS building
- **SQL Server**: Optional for bond schedule data via `pyodbc`

### Environment Setup
- Use conda environments (preferred) with `environment.yml`
- Pin dependencies explicitly in `requirements.txt`
- Prefer conda-forge channel for package installation
- Configure data folder path via environment variable or config
- Separate production and development dependencies

### Windows Desktop Deployment
- `setup_installer.py` creates desktop shortcuts
- `run_app.bat` handles conda activation and browser opening
- Application runs on `localhost:5000` by default

This codebase emphasizes maintainability, extensibility, and transparency. When making changes, follow the established patterns for configuration, error handling, and modular design to ensure consistency with the existing architecture.