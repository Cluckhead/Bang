# Purpose: Central configuration for the sidebar navigation menu.
# This file defines the NAV_MENU dictionary used to render the sidebar in base.html.
#
# Navigation is organized by user workflow and logical groupings:
# - Dashboard & Overview: Main entry points and time-series analysis
# - Security Analysis: Security-level views and comparisons  
# - Fund & Portfolio Analysis: Fund-specific views and portfolio checks
# - Attribution Analysis: All attribution-related functionality
# - Data Quality & Monitoring: Data validation and monitoring tools
# - Data Management: Workflow management (watchlist, issues, exclusions)
# - Data APIs & Tools: Data fetching and simulation tools
#
# Note: Some detail pages (like Attribution Time Series) are accessible through
# summary pages rather than direct navigation links.

NAV_MENU = [
    {
        "section": "Dashboard & Overview",
        "items": [
            {
                "label": "Main Dashboard",
                "endpoint": "main.index",
                "params": {}
            },
            {
                "label": "Time Series Metrics",
                "is_header": True
            },
            {
                "label": "Duration Analysis",
                "endpoint": "metric.metric_page",
                "params": {"metric_name": "duration"}
            },
            {
                "label": "Spread Analysis", 
                "endpoint": "metric.metric_page",
                "params": {"metric_name": "spread"}
            },
            {
                "label": "YTM Analysis",
                "endpoint": "metric.metric_page",
                "params": {"metric_name": "ytm"}
            },
            {
                "label": "YTW Analysis",
                "endpoint": "metric.metric_page",
                "params": {"metric_name": "ytw"}
            },
            {
                "label": "Spread Duration Analysis",
                "endpoint": "metric.metric_page",
                "params": {"metric_name": "spread_duration"}
            }
        ]
    },
            {
            "section": "Security Analysis",
            "items": [
                {
                    "label": "Securities – Spread",
                    "endpoint": "security.securities_page",
                    "params": {}
                },
                {
                    "label": "Securities – Duration",
                    "endpoint": "security.securities_page",
                    "params": {"metric_name": "Duration"}
                },
                {
                    "label": "Securities – YTM",
                    "endpoint": "security.securities_page",
                    "params": {"metric_name": "YTM"}
                },
                {
                    "label": "Securities – YTW",
                    "endpoint": "security.securities_page",
                    "params": {"metric_name": "YTW"}
                },
                {
                    "label": "Securities – Spread Duration",
                    "endpoint": "security.securities_page",
                    "params": {"metric_name": "Spread duration"}
                },
                {
                    "label": "Security Comparisons",
                    "is_header": True
                },
            {
                "label": "Spread Comparison",
                "endpoint": "generic_comparison_bp.summary",
                "params": {"comparison_type": "spread"}
            },
            {
                "label": "Duration Comparison",
                "endpoint": "generic_comparison_bp.summary",
                "params": {"comparison_type": "duration"}
            },
            {
                "label": "Spread Duration Comparison",
                "endpoint": "generic_comparison_bp.summary",
                "params": {"comparison_type": "spread_duration"}
            },
            {
                "label": "YTM Comparison",
                "endpoint": "generic_comparison_bp.summary",
                "params": {"comparison_type": "ytm"}
            },
            {
                "label": "YTW Comparison",
                "endpoint": "generic_comparison_bp.summary",
                "params": {"comparison_type": "ytw"}
            }
        ]
    },
    {
        "section": "Fund & Portfolio Analysis",
        "items": [
            {
                "label": "Fund Selection",
                "endpoint": "main.index",
                "params": {}
            },
            {
                "label": "Portfolio Checks",
                "is_header": True
            },
            {
                "label": "Weight Check",
                "endpoint": "weight.weight_check",
                "params": {}
            },
            {
                "label": "Yield Curve Analysis",
                "endpoint": "curve_bp.curve_summary",
                "params": {}
            },
            {
                "label": "Government Bond Yield Curve",
                "endpoint": "curve_bp.govt_yield_curve",
                "params": {}
            },
            {
                "label": "KRD vs Duration",
                "endpoint": "krd_bp.krd_comparison",
                "params": {}
            }
        ]
    },
    {
        "section": "Attribution Analysis",
        "items": [
            {
                "label": "Attribution Summary",
                "endpoint": "attribution_bp.attribution_summary",
                "params": {}
            },
            {
                "label": "Attribution by Security",
                "endpoint": "attribution_bp.attribution_security_page",
                "params": {}
            },

            {
                "label": "Attribution Radar",
                "endpoint": "attribution_bp.attribution_radar",
                "params": {}
            },
            {
                "label": "Attribution Charts",
                "endpoint": "attribution_bp.attribution_charts",
                "params": {}
            }
        ]
    },
    {
        "section": "Data Quality & Monitoring",
        "items": [
            {
                "label": "Data Consistency Audit",
                "endpoint": "api_bp.get_data_page",
                "params": {}
            },
            {
                "label": "Staleness Detection",
                "endpoint": "staleness_bp.dashboard",
                "params": {}
            },
            {
                "label": "File Delivery Monitor",
                "endpoint": "file_delivery_bp.dashboard",
                "params": {}
            },
            {
                "label": "Max/Min Breach Monitoring",
                "endpoint": "maxmin_bp.dashboard",
                "params": {},
                "subitems": [
                    {
                        "label": "All Breaches",
                        "endpoint": "maxmin_bp.dashboard",
                        "params": {}
                    },
                    {
                        "label": "Yields",
                        "endpoint": "maxmin_bp.dashboard",
                        "params": {"group_name": "Yields"}
                    },
                    {
                        "label": "Spreads",
                        "endpoint": "maxmin_bp.dashboard",
                        "params": {"group_name": "Spreads"}
                    }
                ]
            }
        ]
    },
    {
        "section": "Data Management",
        "items": [
            {
                "label": "Watchlist",
                "endpoint": "watchlist_bp.manage_watchlist",
                "params": {}
            },
            {
                "label": "Issue Tracking",
                "endpoint": "issue_bp.manage_issues",
                "params": {}
            },
            {
                "label": "Security Exclusions",
                "endpoint": "exclusion_bp.manage_exclusions",
                "params": {}
            }
        ]
    },
    {
        "section": "Data APIs & Tools",
        "items": [
            {
                "label": "Get Pi Data",
                "endpoint": "api_bp.get_data_page",
                "params": {}
            },
            {
                "label": "Get Attribution Data",
                "endpoint": "api_bp.get_attribution_data_page",
                "params": {}
            },
            {
                "label": "Bond Calculator",
                "endpoint": "bond_calc_bp.bond_calculator",
                "params": {}
            },
            {
                "label": "Analytics Debug Workstation",
                "endpoint": "bond_calc_bp.analytics_debug_workstation",
                "params": {}
            },
            {
                "label": "Comprehensive Analytics CSV",
                "endpoint": "synth_analytics_bp.analytics_dashboard",
                "params": {}
            }
        ]
    },
    {
        "section": "System Administration",
        "items": [
            {
                "label": "Application Settings",
                "endpoint": "settings_bp.settings_page",
                "params": {}
            }
        ]
    }
] 