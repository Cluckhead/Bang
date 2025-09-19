# models.py
# Purpose: Typed domain models for bonds, schedules, cashflows, curves, and analytics

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class BondReference:
    isin: str
    security_name: str
    coupon_rate: float
    currency: str
    rating: Optional[str] = None
    sector: Optional[str] = None
    ytm_hint: Optional[float] = None


@dataclass
class BondSchedule:
    issue_date: datetime
    first_coupon: datetime
    maturity_date: datetime
    coupon_frequency: int
    day_basis: str


@dataclass
class CallScheduleEntry:
    date: datetime
    price: float


@dataclass
class Cashflow:
    date: datetime
    time_years: float
    coupon: float
    principal: float
    total: float
    accrual_period: float


@dataclass
class Curve:
    times: List[float]
    rates: List[float]


@dataclass
class Analytics:
    ytm: float
    z_spread: float
    g_spread: float
    effective_duration: float
    modified_duration: float
    convexity: float
    spread_duration: float
    key_rate_durations: Dict[str, float]
    oas_standard: Optional[float] = None
    oas_enhanced: Optional[float] = None
    oas_details: Optional[Dict] = None
    calculated: bool = True


