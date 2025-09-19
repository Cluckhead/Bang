# oas_persistent.py
# Purpose: Persistent Hull-White OAS model with calibration storage and caching

from __future__ import annotations

import json
import os
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
from pathlib import Path
import hashlib
import warnings

from .oas_enhanced_v2 import HullWhiteModel, OASCalculator, YieldCurve
from .numerical_methods import newton_raphson_robust

__all__ = [
    "PersistentHullWhiteModel",
    "CalibrationCache",
    "estimate_mean_reversion_from_historical",
    "calibrate_volatility_from_swaptions",
    "create_persistent_hull_white_calculator"
]


# Global cache for calibration parameters
GLOBAL_CALIBRATION_CACHE = {}


class CalibrationCache:
    """
    Manages caching of Hull-White calibration parameters.
    Prevents redundant recalibration for the same market data.
    """
    
    def __init__(self, cache_dir: str = "calibration_cache"):
        """
        Initialize calibration cache.
        
        Parameters
        ----------
        cache_dir : str
            Directory to store cached calibration files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache = {}
        self.max_cache_age_hours = 24  # Expire cache after 24 hours
        
    def get_cache_key(self, curve_date: datetime, currency: str = "USD") -> str:
        """Generate unique cache key for curve date and currency"""
        date_str = curve_date.strftime("%Y%m%d")
        return f"{currency}_{date_str}"
    
    def get_cached_params(self, cache_key: str) -> Optional[Dict]:
        """
        Retrieve cached parameters if available and not expired.
        
        Returns
        -------
        Dict or None
            Cached parameters or None if not found/expired
        """
        # Check memory cache first
        if cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            if self._is_cache_valid(cached):
                return cached
        
        # Check disk cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                    
                # Convert date strings back to datetime
                cached['calibration_time'] = datetime.fromisoformat(cached['calibration_time'])
                cached['curve_date'] = datetime.fromisoformat(cached['curve_date'])
                
                if self._is_cache_valid(cached):
                    # Load into memory cache
                    self.memory_cache[cache_key] = cached
                    return cached
            except Exception as e:
                print(f"Error loading cache: {e}")
        
        return None
    
    def save_params(self, cache_key: str, params: Dict) -> None:
        """
        Save calibration parameters to cache.
        
        Parameters
        ----------
        cache_key : str
            Unique identifier for this calibration
        params : dict
            Calibration parameters to save
        """
        # Add metadata
        params['calibration_time'] = datetime.now()
        params['cache_key'] = cache_key
        
        # Save to memory
        self.memory_cache[cache_key] = params.copy()
        
        # Save to disk
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        # Convert datetime objects for JSON serialization
        save_params = params.copy()
        save_params['calibration_time'] = params['calibration_time'].isoformat()
        save_params['curve_date'] = params['curve_date'].isoformat()
        
        # Sample theta function at specific points for storage
        if 'theta_samples' not in save_params and params.get('theta_function'):
            save_params['theta_samples'] = self._sample_theta(params['theta_function'])
        
        with open(cache_file, 'w') as f:
            json.dump(save_params, f, indent=2, default=str)
        
        print(f"Calibration saved to cache: {cache_key}")
    
    def _is_cache_valid(self, cached: Dict) -> bool:
        """Check if cached data is still valid (not expired)"""
        if 'calibration_time' not in cached:
            return False
        
        age = datetime.now() - cached['calibration_time']
        return age.total_seconds() / 3600 < self.max_cache_age_hours
    
    def _sample_theta(self, theta_function, num_points: int = 100) -> List[Tuple[float, float]]:
        """Sample theta function at specific points for storage"""
        samples = []
        for t in np.linspace(0.1, 30, num_points):
            try:
                value = theta_function(t)
                samples.append((t, float(value)))
            except:
                samples.append((t, 0.0))
        return samples
    
    def clear_cache(self) -> None:
        """Clear all cached calibrations"""
        self.memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
        print("Calibration cache cleared")


class PersistentHullWhiteModel(HullWhiteModel):
    """
    Hull-White model with persistent calibration storage.
    
    Extends the base HullWhiteModel to:
    1. Save calibration results to disk
    2. Load previously calibrated parameters
    3. Cache calibrations to prevent redundant calculations
    4. Calibrate from historical market data
    """
    
    def __init__(self, 
                 mean_reversion: float = 0.1,
                 volatility: float = 0.015,
                 cache_dir: str = "calibration_cache",
                 use_cache: bool = True):
        """
        Initialize persistent Hull-White model.
        
        Parameters
        ----------
        mean_reversion : float
            Speed of mean reversion (a parameter)
        volatility : float
            Instantaneous volatility (σ parameter)
        cache_dir : str
            Directory for storing calibration cache
        use_cache : bool
            Whether to use caching for calibrations
        """
        super().__init__(mean_reversion, volatility)
        self.cache = CalibrationCache(cache_dir) if use_cache else None
        self.calibration_metadata = {}
        
    def calibrate(self, market_data: Dict) -> None:
        """
        Calibrate model with caching support.
        
        Parameters
        ----------
        market_data : dict
            Must contain 'yield_curve' and optionally:
            - 'swaptions': Swaption volatility data
            - 'historical_yields': Historical yield curves
            - 'curve_date': Date of the curve
            - 'currency': Currency (default USD)
        """
        # Extract curve date and currency
        curve_date = market_data.get('curve_date', datetime.now())
        currency = market_data.get('currency', 'USD')
        
        # Check cache first
        if self.cache:
            cache_key = self.cache.get_cache_key(curve_date, currency)
            cached_params = self.cache.get_cached_params(cache_key)
            
            if cached_params:
                print(f"Loading calibration from cache: {cache_key}")
                self._load_from_cache(cached_params)
                return
        
        # Perform full calibration
        print(f"Performing new calibration for {currency} {curve_date.strftime('%Y-%m-%d')}")
        
        # Calibrate mean reversion from historical data if available
        if 'historical_yields' in market_data:
            self._calibrate_mean_reversion(market_data['historical_yields'])
        
        # Call parent calibration (handles yield curve and swaptions)
        super().calibrate(market_data)
        
        # Store calibration metadata
        self.calibration_metadata = {
            'curve_date': curve_date,
            'currency': currency,
            'calibration_method': 'full',
            'data_sources': list(market_data.keys())
        }
        
        # Save to cache
        if self.cache:
            self._save_to_cache(cache_key)
    
    def _calibrate_mean_reversion(self, historical_data) -> None:
        """
        Calibrate mean reversion parameter from historical yield data.
        
        Parameters
        ----------
        historical_data : pd.DataFrame or str
            Historical yield curves (DataFrame or path to CSV)
        """
        print("Calibrating mean reversion from historical data...")
        
        if isinstance(historical_data, str):
            historical_data = pd.read_csv(historical_data)
        
        # Estimate mean reversion using Ornstein-Uhlenbeck process
        self.a = estimate_mean_reversion_from_historical(historical_data)
        print(f"  Mean reversion calibrated: a = {self.a:.4f}")
    
    def _load_from_cache(self, cached_params: Dict) -> None:
        """Load calibration parameters from cache"""
        self.a = cached_params.get('mean_reversion', 0.1)
        self.sigma = cached_params.get('volatility', 0.015)
        
        # Reconstruct theta function from samples
        if 'theta_samples' in cached_params:
            self.theta_function = self._reconstruct_theta(cached_params['theta_samples'])
        
        # Load metadata
        self.calibration_metadata = cached_params.get('metadata', {})
        
        # Mark as calibrated
        self._calibrated_curve = True  # Placeholder to indicate calibration
    
    def _save_to_cache(self, cache_key: str) -> None:
        """Save current calibration to cache"""
        params = {
            'mean_reversion': self.a,
            'volatility': self.sigma,
            'curve_date': self.calibration_metadata.get('curve_date', datetime.now()),
            'metadata': self.calibration_metadata
        }
        
        # Add theta function if available
        if self.theta_function:
            params['theta_function'] = self.theta_function
        
        self.cache.save_params(cache_key, params)
    
    def _reconstruct_theta(self, theta_samples: List[Tuple[float, float]]):
        """Reconstruct theta function from samples using interpolation"""
        from scipy.interpolate import interp1d
        
        if not theta_samples:
            return None
        
        times = [t for t, _ in theta_samples]
        values = [v for _, v in theta_samples]
        
        # Create interpolation function
        return interp1d(times, values, kind='cubic', fill_value='extrapolate')
    
    def save_calibration(self, filepath: str) -> None:
        """
        Save calibration to a specific file.
        
        Parameters
        ----------
        filepath : str
            Path to save calibration file
        """
        params = self.get_calibration_params()
        
        # Add samples of theta function
        if self.theta_function:
            params['theta_samples'] = [(t, float(self.theta_function(t))) 
                                      for t in np.linspace(0.1, 30, 100)]
        
        with open(filepath, 'w') as f:
            json.dump(params, f, indent=2, default=str)
        
        print(f"Calibration saved to {filepath}")
    
    @classmethod
    def load_calibration(cls, filepath: str) -> PersistentHullWhiteModel:
        """
        Load calibrated model from file.
        
        Parameters
        ----------
        filepath : str
            Path to calibration file
            
        Returns
        -------
        PersistentHullWhiteModel
            Calibrated model instance
        """
        with open(filepath, 'r') as f:
            params = json.load(f)
        
        # Create model with loaded parameters
        model = cls(
            mean_reversion=params.get('mean_reversion', 0.1),
            volatility=params.get('volatility', 0.015)
        )
        
        # Reconstruct theta function if available
        if 'theta_samples' in params:
            model.theta_function = model._reconstruct_theta(params['theta_samples'])
        
        # Load metadata
        model.calibration_metadata = params.get('metadata', {})
        
        print(f"Calibration loaded from {filepath}")
        return model
    
    def get_calibration_params(self) -> Dict:
        """Get complete calibration parameters including metadata"""
        params = super().get_parameters()
        params['metadata'] = self.calibration_metadata
        params['calibration_date'] = datetime.now()
        return params


def estimate_mean_reversion_from_historical(historical_data: pd.DataFrame,
                                           rate_column: str = '5Y') -> float:
    """
    Estimate mean reversion parameter from historical yield data.
    
    Uses Ornstein-Uhlenbeck process: dr = a(θ - r)dt + σdW
    
    Parameters
    ----------
    historical_data : pd.DataFrame
        Historical yield curves with date index
    rate_column : str
        Which tenor to use for estimation (default 5Y)
        
    Returns
    -------
    float
        Estimated mean reversion parameter
    """
    # Extract the time series
    if rate_column not in historical_data.columns:
        # Try to find a suitable column
        for col in ['5Y', '10Y', '2Y', '1Y']:
            if col in historical_data.columns:
                rate_column = col
                break
        else:
            raise ValueError(f"No suitable rate column found in {historical_data.columns}")
    
    rates = historical_data[rate_column].values
    
    # Remove any NaN values
    rates = rates[~np.isnan(rates)]
    
    if len(rates) < 100:
        print(f"Warning: Only {len(rates)} observations, using default mean reversion")
        return 0.10
    
    # Calculate daily changes
    dr = np.diff(rates)
    r = rates[:-1]
    
    # Linear regression: dr = -a*r + a*θ + ε
    # Rearranging: dr = beta*r + alpha where beta = -a
    from scipy import stats
    slope, intercept, r_value, p_value, std_err = stats.linregress(r, dr)
    
    # Extract mean reversion (annualized)
    # Assuming daily data with 252 trading days per year
    a = -slope * 252
    
    # Apply reasonable bounds
    a = np.clip(a, 0.01, 0.50)
    
    print(f"  Estimated mean reversion: a = {a:.4f} (R-squared = {r_value**2:.3f})")
    
    return a


def calibrate_volatility_from_swaptions(swaption_data: pd.DataFrame) -> float:
    """
    Calibrate Hull-White volatility parameter from swaption market data.
    
    Parameters
    ----------
    swaption_data : pd.DataFrame
        Swaption volatility data with columns:
        - OptionTenor: Option expiry (e.g., '1Y')
        - SwapTenor: Underlying swap tenor (e.g., '10Y')
        - ImpliedVol: Market implied volatility
        
    Returns
    -------
    float
        Calibrated volatility parameter
    """
    if len(swaption_data) == 0:
        print("Warning: No swaption data, using default volatility")
        return 0.015
    
    # Convert tenors to years
    def tenor_to_years(tenor_str):
        if 'Y' in tenor_str:
            return float(tenor_str.replace('Y', ''))
        elif 'M' in tenor_str:
            return float(tenor_str.replace('M', '')) / 12
        else:
            return float(tenor_str)
    
    # Extract relevant swaptions (focus on liquid points)
    liquid_points = []
    for _, row in swaption_data.iterrows():
        try:
            expiry = tenor_to_years(str(row['OptionTenor']))
            tenor = tenor_to_years(str(row['SwapTenor']))
            vol = float(row['ImpliedVol'])
            
            # Focus on liquid points (1Y-5Y expiry, 5Y-10Y swaps)
            if 0.5 <= expiry <= 5 and 2 <= tenor <= 10:
                liquid_points.append((expiry, tenor, vol))
        except:
            continue
    
    if not liquid_points:
        print("Warning: No liquid swaption points found")
        return 0.015
    
    # Simple calibration: average of short-term volatilities
    # In practice, would use optimization to minimize pricing errors
    short_term_vols = [vol for exp, ten, vol in liquid_points if exp <= 2]
    
    if short_term_vols:
        calibrated_vol = np.mean(short_term_vols) / 100  # Convert from percentage
    else:
        calibrated_vol = np.mean([vol for _, _, vol in liquid_points]) / 100
    
    # Apply reasonable bounds
    calibrated_vol = np.clip(calibrated_vol, 0.001, 0.10)
    
    print(f"  Calibrated volatility from {len(liquid_points)} swaptions: sigma = {calibrated_vol:.4f}")
    
    return calibrated_vol


def create_persistent_hull_white_calculator(
    yield_curve: YieldCurve,
    market_data_path: Optional[str] = None,
    use_cache: bool = True
) -> OASCalculator:
    """
    Create Hull-White OAS calculator with persistent calibration.
    
    Parameters
    ----------
    yield_curve : YieldCurve
        Current yield curve for discounting
    market_data_path : str, optional
        Path to market data directory (e.g., 'hull_white_market_data')
    use_cache : bool
        Whether to use calibration caching
        
    Returns
    -------
    OASCalculator
        Configured OAS calculator with calibrated Hull-White model
    """
    # Initialize persistent model
    hw_model = PersistentHullWhiteModel(use_cache=use_cache)
    
    # Prepare market data for calibration
    calibration_data = {
        'yield_curve': yield_curve,
        'curve_date': yield_curve.curve_date if hasattr(yield_curve, 'curve_date') else datetime.now()
    }
    
    # Load market data if path provided
    if market_data_path:
        market_data_dir = Path(market_data_path)
        
        # Load historical yields
        hist_file = market_data_dir / 'historical' / 'historical_yield_curves.csv'
        if hist_file.exists():
            calibration_data['historical_yields'] = str(hist_file)
            print(f"Using historical data from {hist_file}")
        
        # Load swaption volatilities
        swap_file = market_data_dir / 'market_data' / 'swaption_volatilities.csv'
        if swap_file.exists():
            swaption_df = pd.read_csv(swap_file)
            # Convert to format expected by calibration
            swaption_list = []
            for _, row in swaption_df.head(50).iterrows():  # Use first 50 for speed
                swaption_list.append({
                    'expiry': float(row['OptionTenor'].replace('Y', '').replace('M', '')) / (12 if 'M' in row['OptionTenor'] else 1),
                    'tenor': float(row['SwapTenor'].replace('Y', '')),
                    'implied_vol': row['ImpliedVol'] / 100
                })
            calibration_data['swaptions'] = swaption_list
            print(f"Using {len(swaption_list)} swaption points from {swap_file}")
    
    # Calibrate model
    hw_model.calibrate(calibration_data)
    
    # Show calibrated parameters
    params = hw_model.get_calibration_params()
    print(f"Hull-White calibrated: a={params['mean_reversion']:.4f}, sigma={params['volatility']:.4f}")
    
    # Create and return OAS calculator
    return OASCalculator(hw_model, yield_curve, "MONTE_CARLO")


def test_persistent_calibration():
    """Test the persistent calibration system"""
    print("="*60)
    print("Testing Persistent Hull-White Calibration")
    print("="*60)
    
    # Create mock yield curve
    from datetime import datetime
    dates = [datetime(2024, 7, 15), datetime(2025, 1, 15), datetime(2029, 1, 15)]
    rates = [0.045, 0.047, 0.050]
    curve = YieldCurve(dates, rates, datetime(2024, 1, 15))
    
    # Test 1: Create and calibrate persistent model
    print("\n1. Creating persistent model...")
    model1 = PersistentHullWhiteModel(use_cache=True)
    
    # Calibrate with market data
    model1.calibrate({
        'yield_curve': curve,
        'curve_date': datetime(2024, 1, 15),
        'currency': 'USD'
    })
    
    print(f"   Model 1 calibrated: a={model1.a:.4f}, σ={model1.sigma:.4f}")
    
    # Test 2: Create second model - should use cache
    print("\n2. Creating second model (should use cache)...")
    model2 = PersistentHullWhiteModel(use_cache=True)
    
    model2.calibrate({
        'yield_curve': curve,
        'curve_date': datetime(2024, 1, 15),
        'currency': 'USD'
    })
    
    print(f"   Model 2 parameters: a={model2.a:.4f}, σ={model2.sigma:.4f}")
    
    # Test 3: Save to file
    print("\n3. Saving calibration to file...")
    model1.save_calibration("test_calibration.json")
    
    # Test 4: Load from file
    print("\n4. Loading calibration from file...")
    model3 = PersistentHullWhiteModel.load_calibration("test_calibration.json")
    print(f"   Model 3 loaded: a={model3.a:.4f}, σ={model3.sigma:.4f}")
    
    # Test 5: With market data
    print("\n5. Testing with market data path...")
    if Path("hull_white_market_data").exists():
        calc = create_persistent_hull_white_calculator(
            curve,
            market_data_path="hull_white_market_data",
            use_cache=True
        )
        print("   Calculator created with market data calibration")
    
    print("\n" + "="*60)
    print("Persistent calibration test complete!")
    print("="*60)


if __name__ == "__main__":
    test_persistent_calibration()