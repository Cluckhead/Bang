"""
Security Data Provider - Unified data layer for bond analytics calculations
Ensures consistent data collection and merging across all calculation methods
"""

import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
import threading
import json

logger = logging.getLogger(__name__)


@dataclass
class SecurityData:
    """Container for all security-related data."""
    # Identifiers
    isin: str
    base_isin: str
    security_name: Optional[str] = None
    
    # Pricing
    price: float = 0.0
    accrued_interest: float = 0.0
    
    # Reference data
    coupon_rate: float = 0.0
    coupon_frequency: int = 2
    currency: str = 'USD'
    
    # Schedule data
    maturity_date: Optional[datetime] = None
    issue_date: Optional[datetime] = None
    first_coupon_date: Optional[datetime] = None
    day_basis: str = 'ACT/ACT'
    business_day_convention: str = 'NONE'
    
    # Call features
    callable: bool = False
    call_schedule: Optional[str] = '[]'
    
    # Optional custom payment schedule (JSON string with date/amount lines)
    payment_schedule: Optional[str] = None
    
    # Additional metadata
    security_type: Optional[str] = None
    funds: Optional[str] = None
    
    # Optional amortization schedule (list of {date, amount}) for sinking bonds
    amortization_schedule: Optional[List[Dict[str, Any]]] = None


class SecurityDataProvider:
    """
    Unified data provider for security analytics calculations.
    Provides consistent data loading, normalization, and merging logic.
    """
    
    def __init__(self, data_folder: str):
        """
        Initialize the provider with a data folder.
        
        Args:
            data_folder: Path to the folder containing CSV data files
        """
        self.data_folder = Path(data_folder)
        self._lock = threading.RLock()
        
        # Data containers
        self._price_df: Optional[pd.DataFrame] = None
        self._schedule_df: Optional[pd.DataFrame] = None
        self._reference_df: Optional[pd.DataFrame] = None
        self._accrued_df: Optional[pd.DataFrame] = None
        self._curves_df: Optional[pd.DataFrame] = None
        self._amort_df: Optional[pd.DataFrame] = None
        
        # File modification times for cache invalidation
        self._file_mtimes: Dict[str, float] = {}
        
        # Load all data
        self._load_all_data()
    
    def _load_all_data(self) -> None:
        """Load all CSV files into memory."""
        with self._lock:
            # Load price data
            price_path = self.data_folder / 'sec_Price.csv'
            if price_path.exists():
                self._price_df = pd.read_csv(price_path)
                self._normalize_dataframe_isins(self._price_df)
                self._file_mtimes['price'] = price_path.stat().st_mtime
                logger.info(f"Loaded {len(self._price_df)} securities from sec_Price.csv")
            
            # Load schedule data
            schedule_path = self.data_folder / 'schedule.csv'
            if schedule_path.exists():
                self._schedule_df = pd.read_csv(schedule_path)
                self._normalize_dataframe_isins(self._schedule_df)
                self._file_mtimes['schedule'] = schedule_path.stat().st_mtime
                logger.info(f"Loaded {len(self._schedule_df)} schedules from schedule.csv")
            
            # Load reference data
            reference_path = self.data_folder / 'reference.csv'
            if reference_path.exists():
                self._reference_df = pd.read_csv(reference_path)
                self._normalize_dataframe_isins(self._reference_df)
                self._file_mtimes['reference'] = reference_path.stat().st_mtime
                logger.info(f"Loaded {len(self._reference_df)} references from reference.csv")
            
            # Load accrued data
            accrued_path = self.data_folder / 'sec_accrued.csv'
            if accrued_path.exists():
                self._accrued_df = pd.read_csv(accrued_path)
                self._normalize_dataframe_isins(self._accrued_df)
                self._file_mtimes['accrued'] = accrued_path.stat().st_mtime
                logger.info(f"Loaded {len(self._accrued_df)} accrued records from sec_accrued.csv")
            
            # Load curves data
            curves_path = self.data_folder / 'curves.csv'
            if curves_path.exists():
                self._curves_df = pd.read_csv(curves_path)
                self._file_mtimes['curves'] = curves_path.stat().st_mtime
                logger.info(f"Loaded {len(self._curves_df)} curve points from curves.csv")

            # Load amortization schedules (optional)
            amort_path = self.data_folder / 'amortization.csv'
            if amort_path.exists():
                try:
                    self._amort_df = pd.read_csv(amort_path)
                    self._normalize_dataframe_isins(self._amort_df)
                    self._file_mtimes['amort'] = amort_path.stat().st_mtime
                    logger.info(f"Loaded {len(self._amort_df)} amortization rows from amortization.csv")
                except Exception as e:
                    logger.warning(f"Failed to load amortization.csv: {e}")
    
    def _check_cache_validity(self) -> None:
        """Check if any files have been modified and reload if needed."""
        with self._lock:
            needs_reload = False
            
            # Check each file's modification time
            for file_key, file_name in [
                ('price', 'sec_Price.csv'),
                ('schedule', 'schedule.csv'),
                ('reference', 'reference.csv'),
                ('accrued', 'sec_accrued.csv'),
                ('curves', 'curves.csv'),
                ('amort', 'amortization.csv'),
            ]:
                file_path = self.data_folder / file_name
                if file_path.exists():
                    current_mtime = file_path.stat().st_mtime
                    if file_key in self._file_mtimes:
                        if current_mtime > self._file_mtimes[file_key]:
                            logger.info(f"File {file_name} has been modified, reloading data")
                            needs_reload = True
                            break
            
            if needs_reload:
                self._load_all_data()
    
    def _normalize_dataframe_isins(self, df: pd.DataFrame) -> None:
        """Normalize ISINs in a dataframe in-place."""
        if df is not None and 'ISIN' in df.columns:
            df['ISIN'] = df['ISIN'].apply(self._normalize_isin)
    
    def _normalize_isin(self, isin: Any) -> str:
        """
        Normalize ISIN formatting.
        - Trim whitespace
        - Uppercase
        - Convert various unicode dashes to ASCII '-'
        """
        if pd.isna(isin):
            return ""
        
        isin_str = str(isin).strip().upper()
        
        # Convert unicode dashes to ASCII
        unicode_dashes = [
            '\u2010',  # hyphen
            '\u2011',  # non-breaking hyphen
            '\u2012',  # figure dash
            '\u2013',  # en dash
            '\u2014',  # em dash
            '\u2015',  # horizontal bar
        ]
        
        for dash in unicode_dashes:
            isin_str = isin_str.replace(dash, '-')
        
        return isin_str
    
    def _get_base_isin(self, isin: str) -> str:
        """
        Extract base ISIN by removing hyphenated suffix.
        
        Examples:
            US123456-1 -> US123456
            DE789012-2 -> DE789012
            FR111111 -> FR111111 (no change)
        """
        normalized = self._normalize_isin(isin)
        if '-' in normalized:
            return normalized.split('-')[0]
        return normalized
    
    def get_security_data(self, isin: str, date: str) -> Optional[SecurityData]:
        """
        Get complete security data for a given ISIN and date.
        
        This is the main entry point that returns fully merged data
        with all fallbacks and defaults applied.
        
        Args:
            isin: Security ISIN (will be normalized)
            date: Valuation date
            
        Returns:
            SecurityData object with all available information
        """
        # Check cache validity
        self._check_cache_validity()
        
        # Normalize ISIN
        isin_norm = self._normalize_isin(isin)
        base_isin = self._get_base_isin(isin_norm)
        
        # Create SecurityData object
        data = SecurityData(
            isin=isin_norm,
            base_isin=base_isin
        )
        
        # Get price data
        if self._price_df is not None and not self._price_df.empty:
            price_row = self._get_price_row(isin_norm)
            if price_row is not None:
                data.security_name = price_row.get('Security Name')
                data.security_type = price_row.get('Type')
                data.funds = price_row.get('Funds')
                
                # Get price for specific date
                if date in price_row.index:
                    price_val = price_row.get(date)
                    if pd.notna(price_val):
                        data.price = float(price_val)
                
                # Get currency from price (may be overridden)
                if 'Currency' in price_row.index and pd.notna(price_row.get('Currency')):
                    data.currency = str(price_row.get('Currency'))
                
                # Get callable flag
                if 'Callable' in price_row.index:
                    data.callable = str(price_row.get('Callable')).upper() == 'Y'
        
        # Get reference data (overrides some fields)
        reference_row = self.get_reference_data(isin_norm)
        if reference_row is not None:
            # Coupon rate from reference
            if pd.notna(reference_row.get('Coupon Rate')):
                data.coupon_rate = float(reference_row.get('Coupon Rate'))
            
            # Day count convention from reference (if provided)
            if 'DayCountConvention' in reference_row.index and pd.notna(reference_row.get('DayCountConvention')):
                try:
                    data.day_basis = str(reference_row.get('DayCountConvention'))
                except Exception:
                    pass
            
            # Business day convention from reference (if provided)
            if 'BusinessDayConvention' in reference_row.index and pd.notna(reference_row.get('BusinessDayConvention')):
                try:
                    bdc_val = str(reference_row.get('BusinessDayConvention')).strip().upper()
                    # Normalize common variants
                    if bdc_val in {"NONE", "UNADJUSTED", ""}:
                        data.business_day_convention = 'NONE'
                    elif bdc_val in {"F", "FOLLOWING"}:
                        data.business_day_convention = 'F'
                    elif bdc_val in {"MF", "MODIFIED FOLLOWING", "MODIFIED_FOLLOWING"}:
                        data.business_day_convention = 'MF'
                    elif bdc_val in {"P", "PRECEDING"}:
                        data.business_day_convention = 'P'
                    elif bdc_val in {"MP", "MODIFIED PRECEDING", "MODIFIED_PRECEDING"}:
                        data.business_day_convention = 'MP'
                    else:
                        data.business_day_convention = bdc_val
                except Exception:
                    pass
            
            # Currency override from Position Currency
            for col in ['Position Currency', 'Currency']:
                if col in reference_row.index and pd.notna(reference_row.get(col)):
                    data.currency = str(reference_row.get(col))
                    break
            
            # Call indicator
            if pd.notna(reference_row.get('Call Indicator')):
                data.callable = bool(reference_row.get('Call Indicator'))
            
            # Maturity from reference (if not in schedule)
            if pd.notna(reference_row.get('Maturity Date')):
                mat_str = str(reference_row.get('Maturity Date'))
                data.maturity_date = self._parse_date(mat_str)
        
        # Get schedule data (technical details preferred)
        schedule_row = self.get_schedule_data(isin_norm)
        if schedule_row is not None:
            # Day basis from schedule
            if pd.notna(schedule_row.get('Day Basis')):
                data.day_basis = str(schedule_row.get('Day Basis'))
            
            # Frequency from schedule
            if pd.notna(schedule_row.get('Coupon Frequency')):
                data.coupon_frequency = int(schedule_row.get('Coupon Frequency'))
            
            # Dates from schedule
            if pd.notna(schedule_row.get('Maturity Date')):
                data.maturity_date = self._parse_date(schedule_row.get('Maturity Date'))
            
            if pd.notna(schedule_row.get('Issue Date')):
                data.issue_date = self._parse_date(schedule_row.get('Issue Date'))
            
            if pd.notna(schedule_row.get('First Coupon')):
                data.first_coupon_date = self._parse_date(schedule_row.get('First Coupon'))
            
            # Call schedule from schedule
            if pd.notna(schedule_row.get('Call Schedule')):
                data.call_schedule = str(schedule_row.get('Call Schedule'))
            
            # Optional custom payment schedule
            for col in ['Payment Schedule', 'Custom Payment Schedule', 'Cashflow Schedule']:
                if col in schedule_row.index and pd.notna(schedule_row.get(col)):
                    data.payment_schedule = str(schedule_row.get(col))
                    break
            
            # Coupon rate if not from reference
            if data.coupon_rate == 0.0 and pd.notna(schedule_row.get('Coupon Rate')):
                data.coupon_rate = float(schedule_row.get('Coupon Rate'))
        
        # Get accrued interest
        data.accrued_interest = self.get_accrued_interest(isin_norm, date)

        # Attach amortization schedule (if available)
        try:
            amort_rows = self.get_amortization_schedule(isin_norm)
            if amort_rows:
                data.amortization_schedule = amort_rows
        except Exception as e:
            logger.debug(f"No amortization schedule for {isin_norm}: {e}")
        
        # Apply defaults for missing values
        self._apply_defaults(data, date)
        
        return data
    
    def _get_price_row(self, isin: str) -> Optional[pd.Series]:
        """Get price row for an ISIN."""
        if self._price_df is None or self._price_df.empty:
            return None
        
        # Try exact match
        matches = self._price_df[self._price_df['ISIN'] == isin]
        if not matches.empty:
            return matches.iloc[0]
        
        # Try base ISIN if hyphenated
        if '-' in isin:
            base_isin = self._get_base_isin(isin)
            matches = self._price_df[self._price_df['ISIN'] == base_isin]
            if not matches.empty:
                return matches.iloc[0]
        
        return None
    
    def get_schedule_data(self, isin: str) -> Optional[pd.Series]:
        """
        Get schedule data for an ISIN with fallback to base ISIN.
        
        Args:
            isin: Normalized ISIN
            
        Returns:
            Schedule row or None
        """
        if self._schedule_df is None or self._schedule_df.empty:
            return None
        
        # Try exact match
        matches = self._schedule_df[self._schedule_df['ISIN'] == isin]
        if not matches.empty:
            return matches.iloc[0]
        
        # Try base ISIN
        base_isin = self._get_base_isin(isin)
        if base_isin != isin:
            matches = self._schedule_df[self._schedule_df['ISIN'] == base_isin]
            if not matches.empty:
                logger.debug(f"Using base ISIN {base_isin} for schedule lookup of {isin}")
                return matches.iloc[0]
        
        return None

    def get_amortization_schedule(self, isin: str) -> Optional[List[Dict[str, Any]]]:
        """Return amortization rows for an ISIN as list of dicts {date, amount}."""
        if self._amort_df is None or self._amort_df.empty:
            return None
        try:
            df = self._amort_df
            # Accept common column variants
            date_col = 'Date' if 'Date' in df.columns else 'date'
            amt_col = 'Amount' if 'Amount' in df.columns else ('Principal' if 'Principal' in df.columns else 'amount')
            if 'ISIN' not in df.columns or date_col not in df.columns or amt_col not in df.columns:
                return None
            rows = df[df['ISIN'] == isin]
            if rows.empty and '-' in isin:
                base_isin = self._get_base_isin(isin)
                rows = df[df['ISIN'] == base_isin]
            if rows.empty:
                return None
            out: List[Dict[str, Any]] = []
            for _, r in rows.iterrows():
                try:
                    dt = self._parse_date(r[date_col])
                    amt = float(r[amt_col])
                    if dt is not None and not np.isnan(amt):
                        out.append({'date': dt.strftime('%Y-%m-%d'), 'amount': amt})
                except Exception:
                    continue
            # Sort by date
            out.sort(key=lambda x: x['date'])
            return out if out else None
        except Exception:
            return None
    
    def get_reference_data(self, isin: str) -> Optional[pd.Series]:
        """
        Get reference data for an ISIN with fallback to base ISIN.
        
        Args:
            isin: Normalized ISIN
            
        Returns:
            Reference row or None
        """
        if self._reference_df is None or self._reference_df.empty:
            return None
        
        # Try exact match
        matches = self._reference_df[self._reference_df['ISIN'] == isin]
        if not matches.empty:
            return matches.iloc[0]
        
        # Try base ISIN
        base_isin = self._get_base_isin(isin)
        if base_isin != isin:
            matches = self._reference_df[self._reference_df['ISIN'] == base_isin]
            if not matches.empty:
                logger.debug(f"Using base ISIN {base_isin} for reference lookup of {isin}")
                return matches.iloc[0]
        
        return None
    
    def get_accrued_interest(self, isin: str, date: str) -> float:
        """
        Get accrued interest with multi-level fallback.
        
        Priority:
        1. Exact ISIN, exact date match
        2. Exact ISIN, nearest previous date
        3. Base ISIN, exact date match
        4. Base ISIN, nearest previous date
        5. Schedule accrued interest
        6. Default to 0.0
        
        Args:
            isin: Normalized ISIN
            date: Date string (various formats supported)
            
        Returns:
            Accrued interest value
        """
        if self._accrued_df is None or self._accrued_df.empty:
            return self._get_schedule_accrued(isin)
        
        # Try exact ISIN
        accrued_row = self._accrued_df[self._accrued_df['ISIN'] == isin]
        
        # If not found, try base ISIN
        if accrued_row.empty and '-' in isin:
            base_isin = self._get_base_isin(isin)
            accrued_row = self._accrued_df[self._accrued_df['ISIN'] == base_isin]
            if not accrued_row.empty:
                logger.debug(f"Using base ISIN {base_isin} for accrued lookup of {isin}")
        
        if accrued_row.empty:
            return self._get_schedule_accrued(isin)
        
        # Get the row
        row = accrued_row.iloc[0]
        
        # Try exact date match (handle various date formats)
        date_cols = [c for c in self._accrued_df.columns if c != 'ISIN']
        
        # Try exact match with various formats
        for date_col in date_cols:
            if self._dates_match(date, date_col):
                val = row.get(date_col)
                if pd.notna(val):
                    return float(val)
        
        # Try nearest previous date
        parsed_target = self._parse_date(date)
        if parsed_target:
            available_dates = []
            for col in date_cols:
                parsed_col = self._parse_date(col)
                if parsed_col and parsed_col <= parsed_target:
                    available_dates.append((parsed_col, col))
            
            if available_dates:
                # Sort and get most recent
                available_dates.sort(key=lambda x: x[0])
                _, best_col = available_dates[-1]
                val = row.get(best_col)
                if pd.notna(val):
                    logger.debug(f"Using previous date {best_col} for accrued on {date}")
                    return float(val)
        
        # Fall back to schedule
        return self._get_schedule_accrued(isin)
    
    def _get_schedule_accrued(self, isin: str) -> float:
        """Get accrued from schedule or return 0.0."""
        schedule_row = self.get_schedule_data(isin)
        if schedule_row is not None and pd.notna(schedule_row.get('Accrued Interest')):
            return float(schedule_row.get('Accrued Interest'))
        return 0.0
    
    def get_currency(self, isin: str) -> str:
        """
        Get currency with priority logic.
        
        Priority:
        1. Reference Position Currency
        2. Reference Currency
        3. Price Currency
        4. Default USD
        
        Args:
            isin: Normalized ISIN
            
        Returns:
            Currency code
        """
        # Try reference first
        reference_row = self.get_reference_data(isin)
        if reference_row is not None:
            # Try Position Currency first
            for col in ['Position Currency', 'Currency']:
                if col in reference_row.index and pd.notna(reference_row.get(col)):
                    return str(reference_row.get(col))
        
        # Try price data
        if self._price_df is not None:
            price_row = self._get_price_row(isin)
            if price_row is not None and 'Currency' in price_row.index:
                if pd.notna(price_row.get('Currency')):
                    return str(price_row.get('Currency'))
        
        # Default
        return 'USD'
    
    def get_curves_data(self, currency: str, date: str) -> Optional[pd.DataFrame]:
        """Get curve data for a specific currency and date."""
        if self._curves_df is None or self._curves_df.empty:
            return None
        
        # Filter for currency and date
        date_parsed = self._parse_date(date)
        if date_parsed:
            date_str = date_parsed.strftime('%Y-%m-%d')
            
            filtered = self._curves_df[
                (self._curves_df['Currency Code'] == currency) &
                (self._curves_df['Date'].astype(str).str.startswith(date_str))
            ]
            
            if not filtered.empty:
                return filtered
            
            # Try without date filter
            return self._curves_df[self._curves_df['Currency Code'] == currency]
        
        return None
    
    def _dates_match(self, date1: str, date2: str) -> bool:
        """Check if two date strings represent the same date."""
        parsed1 = self._parse_date(date1)
        parsed2 = self._parse_date(date2)
        
        if parsed1 and parsed2:
            return parsed1.date() == parsed2.date()
        
        # Simple string comparison as fallback
        return date1 == date2
    
    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """
        Parse date string robustly, handling various formats including Excel serial dates.
        """
        if pd.isna(date_str):
            return None
        
        date_str = str(date_str).strip()
        
        # Check for Excel serial number
        try:
            if date_str.replace('.', '').isdigit():
                serial = float(date_str)
                # Excel epoch starts at 1900-01-01
                # Adjust for Excel's leap year bug
                if serial >= 60:
                    serial -= 1
                excel_epoch = datetime(1900, 1, 1)
                return excel_epoch + timedelta(days=serial - 1)
        except:
            pass
        
        # Try various date formats
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%m/%d/%Y',
            '%Y/%m/%d',
            '%d.%m.%Y',
            '%Y%m%d',
            '%Y-%m-%dT%H:%M:%S',  # ISO with time
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.split('T')[0] if 'T' in date_str else date_str, fmt)
            except:
                continue
        
        # Try pandas parser as last resort
        try:
            return pd.to_datetime(date_str)
        except:
            logger.debug(f"Could not parse date: {date_str}")
            return None
    
    def _apply_defaults(self, data: SecurityData, date: str) -> None:
        """
        Apply default values for missing fields.
        
        Args:
            data: SecurityData object to update
            date: Valuation date string
        """
        # Parse valuation date
        val_date = self._parse_date(date)
        if val_date is None:
            val_date = datetime.now()
        
        # Default maturity: 5 years from valuation (preserve exact date)
        if data.maturity_date is None:
            # Use replace to keep same day of month
            try:
                data.maturity_date = val_date.replace(year=val_date.year + 5)
            except ValueError:
                # Handle leap year edge case (Feb 29)
                data.maturity_date = val_date + timedelta(days=5*365)
            logger.debug(f"Using default 5-year maturity for {data.isin}")
        
        # Default issue date: 1 year before valuation (preserve exact date)
        if data.issue_date is None:
            # Use replace to keep same day of month
            try:
                data.issue_date = val_date.replace(year=val_date.year - 1)
            except ValueError:
                # Handle leap year edge case (Feb 29)
                data.issue_date = val_date - timedelta(days=365)
            logger.debug(f"Using default issue date 1 year ago for {data.isin}")
        
        # Default first coupon: 6 months after issue
        if data.first_coupon_date is None and data.issue_date:
            months = 12 // data.coupon_frequency if data.coupon_frequency > 0 else 6
            data.first_coupon_date = data.issue_date + timedelta(days=months*30)
        
        # Coupon rate: already defaulted to 0.0 in SecurityData
        # Frequency: already defaulted to 2 in SecurityData
        # Currency: already defaulted to USD in SecurityData
        # Day basis: already defaulted to ACT/ACT in SecurityData
