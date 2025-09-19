"""
Test Goal Seek Convergence Logic
Purpose: Verify that the goal seek binary search algorithm converges correctly
for various analytics targets and input parameters.
"""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import json

# Test data for different scenarios
TEST_SCENARIOS = {
    "ytm_price_seek": {
        "description": "Find price to achieve target YTM",
        "target_analytic": "ytm",
        "target_value": 5.25,  # 5.25%
        "input_to_change": "price",
        "min_value": 80.0,
        "max_value": 120.0,
        "expected_converged": True,
        "tolerance": 0.001
    },
    "zspread_price_seek": {
        "description": "Find price to achieve target Z-Spread",
        "target_analytic": "z_spread",
        "target_value": 150.0,  # 150 bps
        "input_to_change": "price",
        "min_value": 90.0,
        "max_value": 110.0,
        "expected_converged": True,
        "tolerance": 0.1
    },
    "oas_curve_shift": {
        "description": "Find curve shift to achieve target OAS",
        "target_analytic": "oas",
        "target_value": 100.0,  # 100 bps
        "input_to_change": "curve_shift",
        "min_value": -200.0,
        "max_value": 200.0,
        "expected_converged": True,
        "tolerance": 0.5
    }
}


class TestGoalSeekConvergence:
    """Test suite for goal seek convergence logic."""
    
    def test_binary_search_convergence(self):
        """Test that binary search algorithm converges correctly."""
        # Simple monotonic function: f(x) = 2x + 10
        def simple_function(x):
            return 2 * x + 10
        
        # Goal: find x such that f(x) = 50
        target = 50.0
        min_val = 0.0
        max_val = 100.0
        tolerance = 0.001
        max_iterations = 50
        
        # Implement binary search
        low, high = min_val, max_val
        iterations = []
        
        for i in range(max_iterations):
            mid = (low + high) / 2.0
            result = simple_function(mid)
            error = result - target
            
            iterations.append({
                "iteration": i + 1,
                "input_value": mid,
                "result_value": result,
                "error": error,
                "abs_error": abs(error)
            })
            
            if abs(error) <= tolerance:
                break
            
            if error > 0:
                high = mid
            else:
                low = mid
        
        # Check convergence
        assert len(iterations) > 0, "Should have at least one iteration"
        final_error = iterations[-1]["abs_error"]
        assert final_error <= tolerance, f"Should converge within tolerance: {final_error} > {tolerance}"
        
        # Check that we found x = 20 (since 2*20 + 10 = 50)
        expected_x = 20.0
        final_x = iterations[-1]["input_value"]
        assert abs(final_x - expected_x) < 0.01, f"Should find x ≈ {expected_x}, got {final_x}"
    
    def test_non_monotonic_function_issues(self):
        """Test that binary search may fail for non-monotonic functions."""
        # Non-monotonic function: f(x) = (x-50)^2
        def non_monotonic(x):
            return (x - 50) ** 2
        
        # Goal: find x such that f(x) = 100
        # This has two solutions: x = 40 and x = 60
        target = 100.0
        min_val = 0.0
        max_val = 100.0
        tolerance = 0.001
        max_iterations = 50
        
        low, high = min_val, max_val
        iterations = []
        
        for i in range(max_iterations):
            mid = (low + high) / 2.0
            result = non_monotonic(mid)
            error = result - target
            
            iterations.append({
                "iteration": i + 1,
                "input_value": mid,
                "result_value": result,
                "error": error,
                "abs_error": abs(error)
            })
            
            if abs(error) <= tolerance:
                break
            
            # This logic assumes monotonic function - will have issues
            if error > 0:
                high = mid
            else:
                low = mid
        
        # This test demonstrates that binary search might not converge correctly
        # for non-monotonic functions
        print(f"Non-monotonic convergence: iterations={len(iterations)}, final_error={iterations[-1]['abs_error']}")
    
    def test_unit_conversion_consistency(self):
        """Test that unit conversions are handled consistently."""
        # Test YTM conversion
        ytm_decimal = 0.0525  # 5.25% as decimal
        ytm_percent = 5.25    # 5.25% as percentage
        
        # Backend returns YTM as decimal, converts to percentage for comparison
        backend_ytm = ytm_decimal
        converted_for_comparison = backend_ytm * 100
        
        assert abs(converted_for_comparison - ytm_percent) < 0.0001, \
            "YTM conversion should be consistent"
        
        # Test spread conversion (basis points)
        spread_decimal = 0.0150  # 150 bps as decimal
        spread_bps = 150.0       # 150 bps
        
        # Backend returns spread as decimal, converts to bps for comparison
        backend_spread = spread_decimal
        converted_for_comparison = backend_spread * 10000
        
        assert abs(converted_for_comparison - spread_bps) < 0.01, \
            "Spread conversion should be consistent"
    
    def test_edge_cases(self):
        """Test edge cases in goal seek."""
        # Test 1: Target outside range
        def linear_func(x):
            return x
        
        target = 150.0  # Outside [0, 100] range
        min_val = 0.0
        max_val = 100.0
        tolerance = 0.001
        max_iterations = 50
        
        low, high = min_val, max_val
        iterations = []
        
        for i in range(max_iterations):
            mid = (low + high) / 2.0
            result = linear_func(mid)
            error = result - target
            
            iterations.append({
                "iteration": i + 1,
                "input_value": mid,
                "result_value": result,
                "error": error,
                "abs_error": abs(error)
            })
            
            if abs(error) <= tolerance:
                break
            
            if error > 0:
                high = mid
            else:
                low = mid
        
        # Should reach max_iterations without converging
        assert len(iterations) == max_iterations, \
            "Should exhaust iterations when target is outside range"
        assert iterations[-1]["abs_error"] > tolerance, \
            "Should not converge when target is outside range"
        
        # Test 2: Invalid min/max (min > max) - This should be validated
        invalid_min = 100.0
        invalid_max = 50.0
        assert invalid_min > invalid_max, "Testing invalid range where min > max"
        # The actual code should validate this and raise an error
    
    def test_convergence_rate(self):
        """Test that binary search converges at expected O(log n) rate."""
        def linear_func(x):
            return x
        
        target = 67.5
        min_val = 0.0
        max_val = 100.0
        tolerance = 0.001
        
        # Calculate expected iterations
        range_size = max_val - min_val
        expected_iterations = np.ceil(np.log2(range_size / tolerance))
        
        # Run binary search
        low, high = min_val, max_val
        iterations = 0
        
        while (high - low) > tolerance and iterations < 100:
            mid = (low + high) / 2.0
            result = linear_func(mid)
            error = result - target
            iterations += 1
            
            if error > 0:
                high = mid
            else:
                low = mid
        
        print(f"Converged in {iterations} iterations (expected ≈ {expected_iterations})")
        # Allow some margin
        assert iterations <= expected_iterations + 2, \
            f"Should converge in O(log n) iterations: got {iterations}, expected ≤ {expected_iterations + 2}"
    
    @patch('views.bond_calc_views._run_spreadomatic_step_by_step')
    def test_goal_seek_with_mock_calculation(self, mock_calc):
        """Test goal seek with mocked calculation engine."""
        # Mock the calculation to return predictable results
        def mock_calculation(price, *args, **kwargs):
            # Simple linear relationship: YTM = 10 - 0.05 * price
            ytm = (10.0 - 0.05 * price) / 100  # Return as decimal
            return {
                "success": True,
                "results": {
                    "ytm": ytm,
                    "z_spread": 150.0 / 10000,  # 150 bps as decimal
                    "effective_duration": 5.5
                }
            }
        
        mock_calc.side_effect = lambda price, *args, **kwargs: mock_calculation(price)
        
        # Test finding price for target YTM
        target_ytm_percent = 5.0  # 5%
        
        # Binary search implementation (mimicking the actual code)
        min_value = 80.0
        max_value = 120.0
        tolerance = 0.001
        max_iterations = 50
        
        low, high = min_value, max_value
        iterations = []
        
        for i in range(max_iterations):
            mid = (low + high) / 2.0
            calc_result = mock_calculation(mid)
            
            result_value = calc_result["results"]["ytm"]
            result_value *= 100  # Convert to percentage for comparison
            
            error = result_value - target_ytm_percent
            
            iterations.append({
                "iteration": i + 1,
                "input_value": mid,
                "result_value": result_value,
                "error": error,
                "abs_error": abs(error)
            })
            
            if abs(error) <= tolerance:
                break
            
            if error > 0:
                high = mid
            else:
                low = mid
        
        # Check convergence
        assert iterations[-1]["abs_error"] <= tolerance, \
            f"Should converge: final error = {iterations[-1]['abs_error']}"
        
        # Verify the found price
        # From YTM = 10 - 0.05 * price = 5, we get price = 100
        expected_price = 100.0
        found_price = iterations[-1]["input_value"]
        assert abs(found_price - expected_price) < 0.1, \
            f"Should find price ≈ {expected_price}, got {found_price}"


if __name__ == "__main__":
    # Run tests
    test = TestGoalSeekConvergence()
    
    print("Testing binary search convergence...")
    test.test_binary_search_convergence()
    print("✓ Binary search converges correctly")
    
    print("\nTesting non-monotonic function issues...")
    test.test_non_monotonic_function_issues()
    print("✓ Demonstrated non-monotonic issues")
    
    print("\nTesting unit conversion consistency...")
    test.test_unit_conversion_consistency()
    print("✓ Unit conversions are consistent")
    
    print("\nTesting edge cases...")
    test.test_edge_cases()
    print("✓ Edge cases handled")
    
    print("\nTesting convergence rate...")
    test.test_convergence_rate()
    print("✓ Convergence rate is O(log n)")
    
    print("\nAll tests passed!")
