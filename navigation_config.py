# Purpose: Central configuration for the sidebar navigation menu.
# This file defines the NAV_MENU dictionary used to render the sidebar in base.html.

NAV_MENU = [
    {
        "section": "Data Quality & Audit",
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
                "label": "Max/Min Value Breach",
                "endpoint": "maxmin_bp.dashboard",
                "params": {},
                "subitems": [
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
        "section": "Data Analysis & Comparison",
        "items": [
            {
                "label": "Time Series Dashboard",
                "endpoint": "main.index",
                "params": {}
            },
            {
                "label": "Security-Level Analysis",
                "is_header": True
            },
            {
                "label": "Securities Spread Check",
                "endpoint": "security.securities_page",
                "params": {}
            },
            {
                "label": "Weight Check",
                "endpoint": "weight.weight_check",
                "params": {}
            },
            {
                "label": "Yield Curve Check",
                "endpoint": "curve_bp.curve_summary",
                "params": {}
            },
            {
                "label": "Generic Data Comparison",
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
        "section": "Portfolio & Attribution",
        "items": [
            {
                "label": "Attribution Residuals (Summary)",
                "endpoint": "attribution_bp.attribution_summary",
                "params": {}
            },
            {
                "label": "Attribution Security-Level",
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
        "section": "Issue & Workflow Management",
        "items": [
            {
                "label": "Watchlist",
                "endpoint": "watchlist_bp.manage_watchlist",
                "params": {}
            },
            {
                "label": "Track Issues",
                "endpoint": "issue_bp.manage_issues",
                "params": {}
            },
            {
                "label": "Exclusions",
                "endpoint": "exclusion_bp.manage_exclusions",
                "params": {}
            }
        ]
    }
] 