# Purpose: Caching system for attribution aggregates to improve performance with large (~100MB) attribution files.
# Caches are saved as CSV files with _cached suffix and include timing compatible with loading_times.log
import os
import pandas as pd
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from .attribution_processing import (
    sum_l2s_block,
    sum_l1s_block,
    compute_residual_block,
    calc_residual,
)
from core import config

# Setup logger for timing
def get_timing_logger():
    """Get timing logger for loading_times.log compatibility"""
    logger = logging.getLogger('attribution_cache_timing')
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join('instance', 'loading_times.log'))
        formatter = logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

class AttributionCache:
    """Manages caching of attribution aggregates for performance optimization"""
    
    def __init__(self, data_folder: str):
        self.data_folder = data_folder
        self.cache_folder = os.path.join(data_folder, 'cache')
        self.timing_logger = get_timing_logger()
        
        # Create cache folder if it doesn't exist
        if not os.path.exists(self.cache_folder):
            os.makedirs(self.cache_folder)
    
    def _log_timing(self, operation: str, duration_ms: float, details: str = ""):
        """Log timing information in loading_times.log format"""
        msg = f"OPERATION:attribution_cache | ACTION:{operation} | DURATION:{duration_ms:.2f}ms"
        if details:
            msg += f" | DETAILS:{details}"
        self.timing_logger.info(msg)
    
    def _get_cache_filename(self, fund: str, cache_type: str) -> str:
        """Generate cache filename based on fund and type"""
        return os.path.join(self.cache_folder, f"att_factors_{fund}_{cache_type}_cached.csv")
    
    def _get_source_mtime(self, fund: str) -> Optional[float]:
        """Get modification time of source attribution file"""
        source_file = os.path.join(self.data_folder, f"att_factors_{fund}.csv")
        if os.path.exists(source_file):
            return os.path.getmtime(source_file)
        return None
    
    def _is_cache_valid(self, cache_file: str, source_mtime: float) -> bool:
        """Check if cache file exists and is newer than source"""
        if not os.path.exists(cache_file):
            return False
        cache_mtime = os.path.getmtime(cache_file)
        return cache_mtime >= source_mtime
    
    def compute_daily_aggregates(self, df: pd.DataFrame, fund: str) -> Dict[str, pd.DataFrame]:
        """Compute all daily aggregates for caching"""
        start_time = time.time()
        
        # Get config
        l1_groups = config.ATTRIBUTION_L1_GROUPS
        l2_all = sum(config.ATTRIBUTION_L2_GROUPS.values(), [])
        attr_cols = config.ATTRIBUTION_COLUMNS_CONFIG
        
        # Attribution column prefixes
        pfx_bench = attr_cols['prefixes']['bench']
        pfx_prod = attr_cols['prefixes']['prod']
        pfx_sp_bench = attr_cols['prefixes']['sp_bench']
        pfx_sp_prod = attr_cols['prefixes']['sp_prod']
        l0_bench = attr_cols['prefixes']['l0_bench']
        l0_prod = attr_cols['prefixes']['l0_prod']
        
        results = {
            'daily_l0': [],
            'daily_l1': [],
            'daily_l2': []
        }
        
        # Process by date
        for date, date_group in df.groupby('Date'):
            # L0 aggregates (residuals)
            bench_prod_res = compute_residual_block(date_group, l0_bench, pfx_bench, l2_all)
            bench_sp_res = compute_residual_block(date_group, l0_bench, pfx_sp_bench, l2_all)
            port_prod_res = compute_residual_block(date_group, l0_prod, pfx_prod, l2_all)
            port_sp_res = compute_residual_block(date_group, l0_prod, pfx_sp_prod, l2_all)
            
            # Compute absolute residuals at security level then sum
            bench_prod_abs = date_group.apply(
                lambda row: abs(calc_residual(row, l0_bench, pfx_bench, l2_all)),
                axis=1
            ).sum()
            bench_sp_abs = date_group.apply(
                lambda row: abs(calc_residual(row, l0_bench, pfx_sp_bench, l2_all)),
                axis=1
            ).sum()
            port_prod_abs = date_group.apply(
                lambda row: abs(calc_residual(row, l0_prod, pfx_prod, l2_all)),
                axis=1
            ).sum()
            port_sp_abs = date_group.apply(
                lambda row: abs(calc_residual(row, l0_prod, pfx_sp_prod, l2_all)),
                axis=1
            ).sum()
            
            # --- NEW: Calculate Return (L0 total) and Total Attribution sums ---
            bench_return = date_group[l0_bench].sum() if l0_bench in date_group else 0
            port_return = date_group[l0_prod].sum() if l0_prod in date_group else 0

            bench_total_attrib_prod = sum_l2s_block(date_group, pfx_bench, l2_all)
            bench_total_attrib_sp = sum_l2s_block(date_group, pfx_sp_bench, l2_all)
            port_total_attrib_prod = sum_l2s_block(date_group, pfx_prod, l2_all)
            port_total_attrib_sp = sum_l2s_block(date_group, pfx_sp_prod, l2_all)
            bench_total_attrib_prod_sum = sum(bench_total_attrib_prod)
            bench_total_attrib_sp_sum = sum(bench_total_attrib_sp)
            port_total_attrib_prod_sum = sum(port_total_attrib_prod)
            port_total_attrib_sp_sum = sum(port_total_attrib_sp)
            
            results['daily_l0'].append({
                'Date': date,
                'Fund': fund,
                'Bench_Return': bench_return,
                'Port_Return': port_return,
                'Bench_TotalAttrib_Prod': bench_total_attrib_prod_sum,
                'Bench_TotalAttrib_SP': bench_total_attrib_sp_sum,
                'Port_TotalAttrib_Prod': port_total_attrib_prod_sum,
                'Port_TotalAttrib_SP': port_total_attrib_sp_sum,
                'Bench_Residual_Prod': bench_prod_res,
                'Bench_Residual_SP': bench_sp_res,
                'Port_Residual_Prod': port_prod_res,
                'Port_Residual_SP': port_sp_res,
                'Bench_AbsResidual_Prod': bench_prod_abs,
                'Bench_AbsResidual_SP': bench_sp_abs,
                'Port_AbsResidual_Prod': port_prod_abs,
                'Port_AbsResidual_SP': port_sp_abs
            })
            
            # L1 aggregates
            bench_l1_prod = sum_l1s_block(date_group, pfx_bench, l1_groups)
            bench_l1_sp = sum_l1s_block(date_group, pfx_sp_bench, l1_groups)
            port_l1_prod = sum_l1s_block(date_group, pfx_prod, l1_groups)
            port_l1_sp = sum_l1s_block(date_group, pfx_sp_prod, l1_groups)
            
            # --- NEW: Augment L1 aggregates with Return/Attrib/Residual ---
            bench_l1_total_prod = sum(bench_l1_prod)
            bench_l1_total_sp = sum(bench_l1_sp)
            port_l1_total_prod = sum(port_l1_prod)
            port_l1_total_sp = sum(port_l1_sp)
            
            results['daily_l1'].append({
                'Date': date,
                'Fund': fund,
                'Bench_L1Rates_Prod': bench_l1_prod[0],
                'Bench_L1Rates_SP': bench_l1_sp[0],
                'Bench_L1Credit_Prod': bench_l1_prod[1],
                'Bench_L1Credit_SP': bench_l1_sp[1],
                'Bench_L1FX_Prod': bench_l1_prod[2],
                'Bench_L1FX_SP': bench_l1_sp[2],
                'Port_L1Rates_Prod': port_l1_prod[0],
                'Port_L1Rates_SP': port_l1_sp[0],
                'Port_L1Credit_Prod': port_l1_prod[1],
                'Port_L1Credit_SP': port_l1_sp[1],
                'Port_L1FX_Prod': port_l1_prod[2],
                'Port_L1FX_SP': port_l1_sp[2],
                'Bench_Return': bench_return,
                'Port_Return': port_return,
                'Bench_TotalAttrib_Prod': bench_l1_total_prod,
                'Bench_TotalAttrib_SP': bench_l1_total_sp,
                'Port_TotalAttrib_Prod': port_l1_total_prod,
                'Port_TotalAttrib_SP': port_l1_total_sp,
                'Bench_Residual_Prod': bench_return - bench_l1_total_prod,
                'Bench_Residual_SP': bench_return - bench_l1_total_sp,
                'Port_Residual_Prod': port_return - port_l1_total_prod,
                'Port_Residual_SP': port_return - port_l1_total_sp,
            })
            
            # L2 aggregates
            bench_l2_prod = sum_l2s_block(date_group, pfx_bench, l2_all)
            bench_l2_sp = sum_l2s_block(date_group, pfx_sp_bench, l2_all)
            port_l2_prod = sum_l2s_block(date_group, pfx_prod, l2_all)
            port_l2_sp = sum_l2s_block(date_group, pfx_sp_prod, l2_all)
            
            # --- NEW: Augment L2 aggregates with Return/Attrib/Residual ---
            bench_l2_total_prod = sum(bench_l2_prod)
            bench_l2_total_sp = sum(bench_l2_sp)
            port_l2_total_prod = sum(port_l2_prod)
            port_l2_total_sp = sum(port_l2_sp)
            
            l2_row = {'Date': date, 'Fund': fund}
            for i, col in enumerate(l2_all):
                l2_row[f'Bench_{col}_Prod'] = bench_l2_prod[i]
                l2_row[f'Bench_{col}_SP'] = bench_l2_sp[i]
                l2_row[f'Port_{col}_Prod'] = port_l2_prod[i]
                l2_row[f'Port_{col}_SP'] = port_l2_sp[i]
            
            l2_row.update({
                'Bench_Return': bench_return,
                'Port_Return': port_return,
                'Bench_TotalAttrib_Prod': bench_l2_total_prod,
                'Bench_TotalAttrib_SP': bench_l2_total_sp,
                'Port_TotalAttrib_Prod': port_l2_total_prod,
                'Port_TotalAttrib_SP': port_l2_total_sp,
                'Bench_Residual_Prod': bench_return - bench_l2_total_prod,
                'Bench_Residual_SP': bench_return - bench_l2_total_sp,
                'Port_Residual_Prod': port_return - port_l2_total_prod,
                'Port_Residual_SP': port_return - port_l2_total_sp,
            })
            
            results['daily_l2'].append(l2_row)
        
        # Convert to DataFrames
        for key in results:
            if results[key]:
                results[key] = pd.DataFrame(results[key])
        
        duration_ms = (time.time() - start_time) * 1000
        self._log_timing('compute_aggregates', duration_ms, f"fund={fund}")
        
        return results
    
    def save_cache(self, fund: str, aggregates: Dict[str, pd.DataFrame]):
        """Save computed aggregates to cache files"""
        start_time = time.time()
        saved_files = []
        
        for cache_type, df in aggregates.items():
            if df is not None and not df.empty:
                cache_file = self._get_cache_filename(fund, cache_type)
                df.to_csv(cache_file, index=False)
                saved_files.append(cache_type)
        
        duration_ms = (time.time() - start_time) * 1000
        self._log_timing('save_cache', duration_ms, f"fund={fund}, files={','.join(saved_files)}")
    
    def load_cache(self, fund: str, cache_type: str) -> Optional[pd.DataFrame]:
        """Load cached aggregates if valid"""
        start_time = time.time()
        
        source_mtime = self._get_source_mtime(fund)
        if source_mtime is None:
            return None
        
        cache_file = self._get_cache_filename(fund, cache_type)
        if not self._is_cache_valid(cache_file, source_mtime):
            self._log_timing('cache_miss', 0, f"fund={fund}, type={cache_type}")
            return None
        
        try:
            df = pd.read_csv(cache_file)
            df['Date'] = pd.to_datetime(df['Date'])
            
            duration_ms = (time.time() - start_time) * 1000
            self._log_timing('cache_hit', duration_ms, f"fund={fund}, type={cache_type}")
            return df
        except Exception as e:
            self._log_timing('cache_error', 0, f"fund={fund}, type={cache_type}, error={str(e)}")
            return None
    
    def get_aggregates_with_cache(self, fund: str, level: str = 'L0', 
                                 date_filter: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
                                 characteristics: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Get aggregates, using cache if available, computing if needed"""
        start_time = time.time()
        
        # Determine cache type based on level
        cache_type = f'daily_{level.lower()}'
        
        # Try to load from cache
        cached_df = self.load_cache(fund, cache_type)
        
        if cached_df is not None:
            # Apply filters to cached data
            if date_filter:
                start_date, end_date = date_filter
                cached_df = cached_df[
                    (cached_df['Date'] >= start_date) & 
                    (cached_df['Date'] <= end_date)
                ]
            
            duration_ms = (time.time() - start_time) * 1000
            self._log_timing('get_aggregates_cached', duration_ms, f"fund={fund}, level={level}")
            return cached_df
        
        # Cache miss - need to compute
        source_file = os.path.join(self.data_folder, f"att_factors_{fund}.csv")
        if not os.path.exists(source_file):
            return pd.DataFrame()
        
        # Load source data
        load_start = time.time()
        df = pd.read_csv(source_file)
        df.columns = df.columns.str.strip()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date', 'Fund'])
        
        load_duration_ms = (time.time() - load_start) * 1000
        self._log_timing('load_source', load_duration_ms, f"fund={fund}")
        
        # Compute and save all aggregates
        aggregates = self.compute_daily_aggregates(df, fund)
        self.save_cache(fund, aggregates)
        
        # Return requested level with filters
        result = aggregates.get(cache_type, pd.DataFrame())
        if not result.empty and date_filter:
            start_date, end_date = date_filter
            result = result[
                (result['Date'] >= start_date) & 
                (result['Date'] <= end_date)
            ]
        
        total_duration_ms = (time.time() - start_time) * 1000
        self._log_timing('get_aggregates_computed', total_duration_ms, f"fund={fund}, level={level}")
        
        return result
    
    def refresh_cache(self, fund: str):
        """Force refresh of cache for a specific fund"""
        start_time = time.time()
        
        source_file = os.path.join(self.data_folder, f"att_factors_{fund}.csv")
        if not os.path.exists(source_file):
            return False
        
        # Load and process
        df = pd.read_csv(source_file)
        df.columns = df.columns.str.strip()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date', 'Fund'])
        
        # Compute and save
        aggregates = self.compute_daily_aggregates(df, fund)
        self.save_cache(fund, aggregates)
        
        duration_ms = (time.time() - start_time) * 1000
        self._log_timing('refresh_cache', duration_ms, f"fund={fund}")
        
        return True
    
    def clear_cache(self, fund: Optional[str] = None):
        """Clear cache files for a specific fund or all funds"""
        start_time = time.time()
        cleared_count = 0
        
        if fund:
            # Clear specific fund
            for cache_type in ['daily_l0', 'daily_l1', 'daily_l2']:
                cache_file = self._get_cache_filename(fund, cache_type)
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    cleared_count += 1
        else:
            # Clear all cache files
            for filename in os.listdir(self.cache_folder):
                if filename.endswith('_cached.csv'):
                    os.remove(os.path.join(self.cache_folder, filename))
                    cleared_count += 1
        
        duration_ms = (time.time() - start_time) * 1000
        self._log_timing('clear_cache', duration_ms, f"fund={fund or 'all'}, count={cleared_count}") 