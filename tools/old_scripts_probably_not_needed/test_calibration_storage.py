#!/usr/bin/env python
"""
Test script to show how calibration results are stored (or not stored)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pandas as pd
import json
import pickle

# Import Hull-White modules
from tools.SpreadOMatic.spreadomatic.oas_enhanced_v2 import (
    HullWhiteModel,
    YieldCurve
)

def test_calibration_storage():
    """Test how calibration results are stored"""
    print("="*60)
    print("Testing Hull-White Calibration Storage")
    print("="*60)
    
    # Load market data
    print("\n1. Loading market data...")
    yield_curve_df = pd.read_csv("hull_white_market_data/market_data/yield_curves.csv")
    latest_date = yield_curve_df['Date'].max()
    curve_data = yield_curve_df[yield_curve_df['Date'] == latest_date]
    
    # Create yield curve
    usd_curve = curve_data[curve_data['Currency'] == 'USD'].sort_values('TenorDays')
    dates = []
    rates = []
    base_date = datetime(2024, 1, 15)
    
    for _, row in usd_curve.iterrows():
        days = int(row['TenorDays'])
        date = base_date + pd.Timedelta(days=days)
        dates.append(date)
        rates.append(row['Rate'] / 100)
    
    yield_curve = YieldCurve(dates, rates, base_date)
    
    # Create and calibrate model
    print("\n2. Creating Hull-White model...")
    hw_model = HullWhiteModel(
        mean_reversion=0.1,  # Initial guess
        volatility=0.015     # Initial guess
    )
    
    print(f"   Initial parameters:")
    print(f"   - Mean reversion: {hw_model.a}")
    print(f"   - Volatility: {hw_model.sigma}")
    print(f"   - Theta function: {hw_model.theta_function}")
    print(f"   - Calibrated curve: {hw_model._calibrated_curve}")
    
    # Calibrate
    print("\n3. Calibrating model...")
    hw_model.calibrate({'yield_curve': yield_curve})
    
    print(f"   After calibration:")
    print(f"   - Mean reversion: {hw_model.a} (UNCHANGED - not calibrated)")
    print(f"   - Volatility: {hw_model.sigma} (UNCHANGED - no swaptions)")
    print(f"   - Theta function: {hw_model.theta_function} (NEW FUNCTION)")
    print(f"   - Calibrated curve: {hw_model._calibrated_curve} (STORED IN MEMORY)")
    
    # Check what's stored
    print("\n4. What gets stored?")
    print("   IN MEMORY (temporary):")
    print(f"   - self.a = {hw_model.a}")
    print(f"   - self.sigma = {hw_model.sigma}")
    print(f"   - self.theta_function = <function object>")
    print(f"   - self._calibrated_curve = <YieldCurve object>")
    
    print("\n   ON DISK (persistent):")
    print("   - NOTHING! Calibration results are NOT saved")
    
    # Show that calibration is lost
    print("\n5. Creating new model instance...")
    hw_model2 = HullWhiteModel(
        mean_reversion=0.1,
        volatility=0.015
    )
    print(f"   New model has no calibration:")
    print(f"   - Theta function: {hw_model2.theta_function} (None)")
    print(f"   - Calibrated curve: {hw_model2._calibrated_curve} (None)")
    
    # How to save calibration (not implemented but could be)
    print("\n6. How calibration COULD be saved:")
    
    print("\n   Option 1: Save parameters to JSON")
    calibration_results = {
        'calibration_date': datetime.now().isoformat(),
        'mean_reversion': hw_model.a,
        'volatility': hw_model.sigma,
        'has_theta_function': hw_model.theta_function is not None,
        'curve_date': base_date.isoformat()
    }
    print(f"   {json.dumps(calibration_results, indent=2)}")
    
    print("\n   Option 2: Pickle the entire model")
    print("   # pickle.dump(hw_model, open('calibrated_model.pkl', 'wb'))")
    print("   # But theta_function is a closure - may not pickle well")
    
    print("\n   Option 3: Save calibration parameters only")
    params = hw_model.get_parameters()
    print(f"   Parameters dict: {params}")
    
    # Show where calibration happens in the call chain
    print("\n7. Calibration lifecycle:")
    print("   a) User calculates bond OAS")
    print("   b) create_hull_white_calculator() called")
    print("   c) HullWhiteModel created with FIXED parameters")
    print("   d) calibrate() called with yield curve")
    print("   e) Only theta_function is calibrated")
    print("   f) Model used for ONE calculation")
    print("   g) Model object destroyed (calibration lost)")
    print("   h) Next bond: repeat entire process")
    
    # Check if swaption calibration would store differently
    print("\n8. If we had swaption data:")
    
    # Mock swaption data
    swaption_data = [
        {'expiry': 1.0, 'tenor': 5.0, 'implied_vol': 0.80},
        {'expiry': 2.0, 'tenor': 5.0, 'implied_vol': 0.75},
        {'expiry': 5.0, 'tenor': 5.0, 'implied_vol': 0.70},
    ]
    
    print("   Calibrating with swaptions...")
    hw_model3 = HullWhiteModel(0.1, 0.015)
    hw_model3.calibrate({
        'yield_curve': yield_curve,
        'swaptions': swaption_data
    })
    
    print(f"   After swaption calibration:")
    print(f"   - Volatility: {hw_model3.sigma} (WOULD BE UPDATED)")
    print(f"   - Still not saved to disk!")
    
    print("\n" + "="*60)
    print("SUMMARY: Calibration Storage")
    print("="*60)
    print("[X] NO PERSISTENT STORAGE - all calibration is lost after use")
    print("[X] Parameters recalibrated for EVERY bond")
    print("[X] No caching mechanism")
    print("[X] No way to save/load calibrated models")
    print("[X] Historical data never used (no connection)")
    print("\nThe calibration exists only in memory during calculation!")
    print("="*60)

if __name__ == "__main__":
    test_calibration_storage()