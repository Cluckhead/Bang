# numerical_methods.py
# Purpose: Robust numerical methods for fixed income calculations
# Implements Brent's method, adaptive quadrature, and other institutional-grade numerical techniques

from __future__ import annotations

import numpy as np
import scipy.optimize as opt
from scipy import integrate
from typing import Callable, Optional, Tuple, Union, Dict, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import warnings
import math

__all__ = [
    "RootFindingMethod",
    "IntegrationMethod", 
    "brent_solve",
    "newton_raphson_robust",
    "adaptive_quadrature",
    "yield_solver",
    "spread_solver", 
    "NumericalConfig"
]


@dataclass
class NumericalConfig:
    """Configuration for numerical methods"""
    tolerance: float = 1e-8
    max_iterations: int = 100
    bracket_expansion_factor: float = 2.0
    initial_bracket_size: float = 0.01
    use_derivative: bool = True
    relative_tolerance: bool = True


class RootFindingMethod(ABC):
    """Abstract base class for root finding methods"""
    
    def __init__(self, config: Optional[NumericalConfig] = None):
        self.config = config or NumericalConfig()
    
    @abstractmethod
    def solve(self, func: Callable[[float], float], 
              initial_guess: float,
              bounds: Optional[Tuple[float, float]] = None) -> float:
        """Solve f(x) = 0"""
        pass


class BrentMethod(RootFindingMethod):
    """
    Brent's method for robust root finding.
    
    Combines the reliability of bisection with the speed of secant method.
    Guaranteed convergence if root is bracketed.
    """
    
    def solve(self, func: Callable[[float], float], 
              initial_guess: float,
              bounds: Optional[Tuple[float, float]] = None) -> float:
        """
        Solve using Brent's method with automatic bracketing.
        
        Args:
            func: Function to find root of
            initial_guess: Starting point for root search
            bounds: Optional bounds (a, b) where f(a)*f(b) < 0
            
        Returns:
            Root of the function
        """
        if bounds is None:
            bounds = self._auto_bracket(func, initial_guess)
        
        a, b = bounds
        fa, fb = func(a), func(b)
        
        # Ensure f(a) and f(b) have opposite signs
        if fa * fb >= 0:
            bounds = self._expand_bracket(func, a, b)
            a, b = bounds
            fa, fb = func(a), func(b)
            
            if fa * fb >= 0:
                raise ValueError("Cannot bracket root: f(a) and f(b) have same sign")
        
        # Ensure |f(a)| >= |f(b)|
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa
        
        c, fc = a, fa
        d = e = b - a
        
        for iteration in range(self.config.max_iterations):
            if abs(fb) < self.config.tolerance:
                return b
            
            if abs(fc) < abs(fb):
                a, b, c = b, c, b
                fa, fb, fc = fb, fc, fb
            
            # Check convergence
            tol = 2 * np.finfo(float).eps * abs(b) + 0.5 * self.config.tolerance
            m = 0.5 * (c - b)
            
            if abs(m) <= tol or abs(fb) < self.config.tolerance:
                return b
            
            # Decide on bisection or interpolation
            if abs(e) >= tol and abs(fa) > abs(fb):
                s = fb / fa
                
                if abs(c - a) < np.finfo(float).eps:
                    # Linear interpolation
                    p = 2 * m * s
                    q = 1 - s
                else:
                    # Inverse quadratic interpolation
                    q = fa / fc
                    r = fb / fc
                    p = s * (2 * m * q * (q - r) - (b - a) * (r - 1))
                    q = (q - 1) * (r - 1) * (s - 1)
                
                if p > 0:
                    q = -q
                else:
                    p = -p
                
                s = e
                e = d
                
                if 2 * p < min(3 * m * q - abs(tol * q), abs(s * q)):
                    d = p / q  # Use interpolation
                else:
                    d = m      # Use bisection
                    e = d
            else:
                d = m          # Use bisection
                e = d
            
            a, fa = b, fb
            
            if abs(d) > tol:
                b += d
            else:
                b += np.copysign(tol, m)
            
            fb = func(b)
            
            if fb * fc > 0:
                c, fc = a, fa
                d = e = b - a
        
        warnings.warn(f"Brent's method did not converge after {self.config.max_iterations} iterations")
        return b
    
    def _auto_bracket(self, func: Callable[[float], float], 
                     initial_guess: float) -> Tuple[float, float]:
        """Automatically bracket the root around initial guess"""
        h = self.config.initial_bracket_size
        x0 = initial_guess
        
        # Try initial bracket
        a, b = x0 - h, x0 + h
        fa, fb = func(a), func(b)
        
        if fa * fb < 0:
            return (a, b)
        
        # Expand bracket systematically
        for _ in range(20):  # Maximum expansions
            if abs(fa) < abs(fb):
                # Expand leftward
                a = x0 - h
                h *= self.config.bracket_expansion_factor
            else:
                # Expand rightward  
                b = x0 + h
                h *= self.config.bracket_expansion_factor
            
            fa, fb = func(a), func(b)
            
            if fa * fb < 0:
                return (a, b)
        
        raise ValueError(f"Could not bracket root around {initial_guess}")
    
    def _expand_bracket(self, func: Callable[[float], float],
                       a: float, b: float) -> Tuple[float, float]:
        """Expand given bracket until signs are opposite"""
        fa, fb = func(a), func(b)
        
        for _ in range(10):
            if fa * fb < 0:
                return (a, b)
            
            # Expand in direction of smaller function value
            if abs(fa) < abs(fb):
                a = a - (b - a)
            else:
                b = b + (b - a)
            
            fa, fb = func(a), func(b)
        
        raise ValueError("Could not expand bracket to opposite signs")


class NewtonRaphsonRobust(RootFindingMethod):
    """
    Robust Newton-Raphson with safeguards and fallback.
    
    Uses numerical derivatives if analytical derivative not provided.
    Falls back to Brent's method if Newton-Raphson fails.
    """
    
    def solve(self, func: Callable[[float], float],
              initial_guess: float,
              bounds: Optional[Tuple[float, float]] = None,
              derivative: Optional[Callable[[float], float]] = None) -> float:
        """
        Solve using robust Newton-Raphson method.
        
        Args:
            func: Function to find root of
            initial_guess: Starting point
            bounds: Optional bounds for safety
            derivative: Optional analytical derivative
        
        Returns:
            Root of the function
        """
        x = initial_guess
        
        # Numerical derivative function if not provided
        if derivative is None:
            def numerical_derivative(x_val: float) -> float:
                h = max(abs(x_val) * 1e-8, 1e-8)
                return (func(x_val + h) - func(x_val - h)) / (2 * h)
            
            derivative = numerical_derivative
        
        # Newton-Raphson iterations
        for iteration in range(self.config.max_iterations):
            fx = func(x)
            
            # Check convergence
            if abs(fx) < self.config.tolerance:
                return x
            
            # Calculate derivative
            try:
                dfx = derivative(x)
                if abs(dfx) < 1e-14:  # Avoid division by very small numbers
                    break  # Fall back to Brent's method
                
                # Newton-Raphson step
                x_new = x - fx / dfx
                
                # Apply bounds if provided
                if bounds is not None:
                    x_new = max(bounds[0], min(bounds[1], x_new))
                
                # Check for reasonable step size
                step_size = abs(x_new - x)
                if step_size > 100 * abs(x):  # Step too large
                    break  # Fall back to Brent's method
                
                # Convergence check
                if step_size < self.config.tolerance * (1 + abs(x)):
                    return x_new
                
                x = x_new
                
            except (ZeroDivisionError, OverflowError, ValueError):
                break  # Fall back to Brent's method
        
        # Fall back to Brent's method if Newton-Raphson fails
        try:
            brent_solver = BrentMethod(self.config)
            return brent_solver.solve(func, initial_guess, bounds)
        except ValueError as e:
            raise ValueError(f"Both Newton-Raphson and Brent's method failed: {e}")


class AdaptiveIntegrator:
    """
    Adaptive numerical integration with error control.
    
    Uses adaptive quadrature with automatic subdivision for accuracy.
    """
    
    def __init__(self, tolerance: float = 1e-8, max_subdivisions: int = 50):
        self.tolerance = tolerance
        self.max_subdivisions = max_subdivisions
    
    def integrate(self, func: Callable[[float], float],
                 a: float, b: float) -> Tuple[float, float]:
        """
        Adaptive integration using scipy's quad with error estimate.
        
        Returns:
            Tuple of (integral_value, error_estimate)
        """
        try:
            result, error = integrate.quad(
                func, a, b, 
                epsabs=self.tolerance,
                epsrel=self.tolerance,
                limit=self.max_subdivisions
            )
            return result, error
        except integrate.IntegrationWarning as w:
            warnings.warn(f"Integration warning: {w}")
            return result, error
        except Exception as e:
            # Fallback to simple trapezoidal rule
            return self._trapezoidal_fallback(func, a, b), float('inf')
    
    def _trapezoidal_fallback(self, func: Callable[[float], float],
                             a: float, b: float, n: int = 1000) -> float:
        """Fallback trapezoidal integration"""
        x = np.linspace(a, b, n+1)
        y = np.array([func(xi) for xi in x])
        return np.trapz(y, x)


def brent_solve(func: Callable[[float], float],
               initial_guess: float,
               bounds: Optional[Tuple[float, float]] = None,
               tolerance: float = 1e-8,
               max_iterations: int = 100) -> float:
    """
    Convenient wrapper for Brent's method root finding.
    
    Args:
        func: Function to find root of (f(x) = 0)
        initial_guess: Starting point for search
        bounds: Optional (min, max) bounds
        tolerance: Convergence tolerance
        max_iterations: Maximum number of iterations
    
    Returns:
        Root of the function
        
    Example:
        >>> def f(x): return x**2 - 2  # Find sqrt(2)
        >>> root = brent_solve(f, 1.0)  # Returns ~1.414
    """
    config = NumericalConfig(tolerance=tolerance, max_iterations=max_iterations)
    solver = BrentMethod(config)
    return solver.solve(func, initial_guess, bounds)


def newton_raphson_robust(func: Callable[[float], float],
                         initial_guess: float,
                         derivative: Optional[Callable[[float], float]] = None,
                         bounds: Optional[Tuple[float, float]] = None,
                         tolerance: float = 1e-8) -> float:
    """
    Robust Newton-Raphson with automatic fallback to Brent's method.
    
    Args:
        func: Function to find root of
        initial_guess: Starting point
        derivative: Optional analytical derivative
        bounds: Optional bounds for safety
        tolerance: Convergence tolerance
    
    Returns:
        Root of the function
    """
    config = NumericalConfig(tolerance=tolerance)
    solver = NewtonRaphsonRobust(config)
    return solver.solve(func, initial_guess, bounds, derivative)


def adaptive_quadrature(func: Callable[[float], float],
                       a: float, b: float,
                       tolerance: float = 1e-8) -> float:
    """
    Adaptive numerical integration.
    
    Args:
        func: Function to integrate
        a: Lower bound
        b: Upper bound  
        tolerance: Error tolerance
    
    Returns:
        Integral value
    """
    integrator = AdaptiveIntegrator(tolerance)
    result, error = integrator.integrate(func, a, b)
    return result


class YieldSolver:
    """Specialized solver for bond yield calculations"""
    
    def __init__(self, config: Optional[NumericalConfig] = None):
        self.config = config or NumericalConfig()
        self.brent_solver = BrentMethod(self.config)
        self.newton_solver = NewtonRaphsonRobust(self.config)
    
    def solve_ytm(self, price: float, cashflows: list, 
                  times: list, initial_guess: float = 0.05) -> float:
        """
        Solve for yield to maturity using robust methods.
        
        Args:
            price: Current bond price
            cashflows: List of cashflow amounts
            times: List of payment times (in years)
            initial_guess: Starting yield guess
        
        Returns:
            Yield to maturity (as decimal)
        """
        def price_function(ytm: float) -> float:
            """Calculate theoretical price minus market price"""
            theoretical_price = sum(
                cf * np.exp(-ytm * t) for cf, t in zip(cashflows, times)
            )
            return theoretical_price - price
        
        def price_derivative(ytm: float) -> float:
            """Derivative of price with respect to yield"""
            return -sum(
                cf * t * np.exp(-ytm * t) for cf, t in zip(cashflows, times)
            )
        
        # Try Newton-Raphson first (faster convergence)
        try:
            return self.newton_solver.solve(
                price_function, initial_guess, (0.0, 1.0), price_derivative
            )
        except ValueError:
            # Fall back to Brent's method
            return self.brent_solver.solve(price_function, initial_guess, (0.001, 0.5))
    
    def solve_spread(self, price: float, cashflows: list,
                    times: list, base_rates: list,
                    initial_guess: float = 0.01) -> float:
        """
        Solve for spread over base curve.
        
        Args:
            price: Current bond price
            cashflows: List of cashflow amounts  
            times: List of payment times
            base_rates: Base rates at each time point
            initial_guess: Starting spread guess
        
        Returns:
            Spread over base curve (as decimal)
        """
        def spread_function(spread: float) -> float:
            theoretical_price = sum(
                cf * np.exp(-(base_rate + spread) * t) 
                for cf, t, base_rate in zip(cashflows, times, base_rates)
            )
            return theoretical_price - price
        
        return self.brent_solver.solve(spread_function, initial_guess, (-0.1, 0.2))


def yield_solver(price: float, cashflows: list, times: list,
                initial_guess: float = 0.05) -> float:
    """
    Convenient function to solve for yield to maturity.
    
    Uses robust numerical methods with automatic fallback.
    """
    solver = YieldSolver()
    return solver.solve_ytm(price, cashflows, times, initial_guess)


def spread_solver(price: float, cashflows: list, times: list, 
                 base_rates: list, initial_guess: float = 0.01) -> float:
    """
    Convenient function to solve for spread over base curve.
    """
    solver = YieldSolver()
    return solver.solve_spread(price, cashflows, times, base_rates, initial_guess)


def validate_numerical_methods():
    """Validation suite for numerical methods"""
    print("Testing Numerical Methods...")
    
    # Test 1: Brent's method for simple quadratic
    def quadratic(x):
        return x**2 - 2  # Root at sqrt(2) ≈ 1.414
    
    root = brent_solve(quadratic, 1.0)
    print(f"Brent's method - sqrt(2): {root:.10f} (error: {abs(root - math.sqrt(2)):.2e})")
    
    # Test 2: Newton-Raphson with derivative
    def cubic(x):
        return x**3 - x - 1  # Root ≈ 1.324717957
    
    def cubic_derivative(x):
        return 3*x**2 - 1
    
    root = newton_raphson_robust(cubic, 1.5, cubic_derivative)
    true_root = 1.3247179572447
    print(f"Newton-Raphson - cubic root: {root:.10f} (error: {abs(root - true_root):.2e})")
    
    # Test 3: Adaptive integration
    def integrand(x):
        return np.exp(-x**2)  # Gaussian, integral from 0 to inf = sqrt(pi)/2
    
    integral = adaptive_quadrature(integrand, 0, 5)  # 5 ≈ infinity for this function
    true_value = math.sqrt(math.pi) / 2
    print(f"Adaptive integration - Gaussian: {integral:.8f} (error: {abs(integral - true_value):.2e})")
    
    # Test 4: YTM solver
    # 5% coupon bond, 2-year maturity, semiannual payments
    cashflows = [2.5, 2.5, 2.5, 102.5]  # 2.5% coupons + principal
    times = [0.5, 1.0, 1.5, 2.0]
    price = 100.0  # Par value
    
    ytm = yield_solver(price, cashflows, times)
    print(f"YTM solver - par bond: {ytm*100:.4f}% (should be ~5.00%)")
    
    print("Numerical methods validation complete!")


if __name__ == "__main__":
    validate_numerical_methods()
