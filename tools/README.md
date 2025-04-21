# Staleness Detection Tools

This directory contains diagnostic and testing tools for the staleness detection system.

## Tools Overview

### 1. Direct Testing (direct_test.py)

A tool for directly checking a specific security for staleness:

```bash
python tools/direct_test.py [SECURITY_ID]
```

Example:
```bash
python tools/direct_test.py XS4035425
```

This will:
- Print detailed information about the specified security
- Show all its values and mark which ones are placeholders
- Display count of consecutive placeholder values
- Indicate whether it should be detected as stale

### 2. Debug Tool (debug_security.py)

A more detailed debugging tool that outputs complete diagnostic information:

```bash
python tools/debug_security.py [SECURITY_ID]
```

Example:
```bash
python tools/debug_security.py XS4035425
```

This provides:
- Complete metadata about the security
- Value-by-value breakdown
- Analysis of placeholder patterns
- Start and end dates of staleness

### 3. System Validation (test_staleness.py)

Tool for testing the staleness detection on a full CSV file:

```bash
python tools/test_staleness.py DATA_FILE [--threshold DAYS] [--check-security SECURITY_ID]
```

Example:
```bash
python tools/test_staleness.py Data/sec_Spread.csv --check-security XS4035425
```

This will:
- Run the production staleness detection algorithm
- List all stale securities found
- Check if a specific security is detected as stale

## Development Usage

These tools are primarily for development and troubleshooting. For production use, refer to:

- `staleness_detection.py` - Standalone command-line tool for analyzing data files
- `staleness_processing.py` - Core module that integrates with the web dashboard

## How to Add New Diagnostic Tools

When adding new diagnostic tools, please:

1. Place them in this `/tools` directory
2. Add documentation to this README
3. Keep testing logic separate from production code 