"""
Settings loader module for Simple Data Checker.
Provides centralized access to all configuration settings from the combined settings.yaml file.
"""

import os
import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Path to the combined settings file
# Always resolve relative to the project root (parent of core/)
_CORE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CORE_DIR.parent
SETTINGS_FILE = _PROJECT_ROOT / 'settings.yaml'

# Cache for loaded settings to avoid repeated file reads
_settings_cache = None
_cache_mtime = None

def load_settings():
    """
    Load settings from the combined YAML file with caching.
    Returns the full settings dictionary.
    """
    global _settings_cache, _cache_mtime
    
    try:
        settings_path = Path(SETTINGS_FILE)
        
        # Check if we need to reload (file changed or not cached)
        if settings_path.exists():
            current_mtime = settings_path.stat().st_mtime
            if _settings_cache is None or _cache_mtime != current_mtime:
                with open(settings_path, 'r') as f:
                    _settings_cache = yaml.safe_load(f)
                _cache_mtime = current_mtime
                logger.info("Loaded settings from combined settings.yaml")
            return _settings_cache
        else:
            logger.warning(f"Settings file {SETTINGS_FILE} not found, using defaults")
            return {}
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        return {}

def get_app_config():
    """Get application configuration settings."""
    settings = load_settings()
    return settings.get('app_config', {})

def get_spread_files():
    """Get spread files configuration."""
    settings = load_settings()
    spread_config = settings.get('spread_files', {})
    return spread_config.get('spread_files', [])

def get_metric_file_map():
    """Get metric file mappings."""
    settings = load_settings()
    metric_config = settings.get('metric_file_map', {})
    return metric_config.get('metrics', {})

def get_data_extender_settings():
    """Get data extender settings."""
    settings = load_settings()
    return settings.get('data_extender_settings', {})

def get_file_delivery_monitors():
    """Get file delivery monitor configurations."""
    settings = load_settings()
    file_delivery = settings.get('file_delivery', {})
    return file_delivery.get('monitors', {})

def get_maxmin_thresholds():
    """Get max/min threshold configurations."""
    settings = load_settings()
    return settings.get('maxmin_thresholds', {})

def get_attribution_columns():
    """Get attribution column configurations."""
    settings = load_settings()
    return settings.get('attribution_columns', {
        'prefixes': {},
        'l1_factors': [],
        'l2_groups': {}
    })

def get_date_patterns():
    """Get date pattern configurations."""
    settings = load_settings()
    date_config = settings.get('date_patterns', {})
    return date_config.get('date_patterns', [])

def get_field_aliases():
    """Get field alias configurations."""
    settings = load_settings()
    return settings.get('field_aliases', {})

def get_comparison_config():
    """Get comparison configurations."""
    settings = load_settings()
    return settings.get('comparison_config', {})

def get_settlement_conventions():
    """Get settlement conventions configuration."""
    settings = load_settings()
    # First try to load from main settings
    settlement = settings.get('settlement_conventions')
    if settlement:
        return settlement
    
    # If not in main settings, try to load from separate file
    try:
        config_path = Path('config/settlement_conventions.yaml')
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading settlement conventions: {e}")
    
    return {}

def get_currency_settlement(currency):
    """Get settlement conventions for a specific currency."""
    conventions = get_settlement_conventions()
    currency_conventions = conventions.get('currency_conventions', {})
    return currency_conventions.get(currency, {})

def get_security_type_settlement(security_type):
    """Get settlement conventions for a specific security type."""
    conventions = get_settlement_conventions()
    security_conventions = conventions.get('security_type_conventions', {})
    return security_conventions.get(security_type, {})

def get_settlement_days(currency=None, security_type=None, trade_type='standard'):
    """Get settlement days (T+n) for a given currency and/or security type."""
    conventions = get_settlement_conventions()
    
    # Try security type first (more specific)
    if security_type:
        sec_conventions = conventions.get('security_type_conventions', {})
        if security_type in sec_conventions:
            sec_data = sec_conventions[security_type]
            if trade_type in sec_data:
                return sec_data[trade_type]
            elif 'standard' in sec_data:
                return sec_data['standard']
    
    # Fall back to currency conventions
    if currency:
        curr_conventions = conventions.get('currency_conventions', {})
        if currency in curr_conventions:
            curr_data = curr_conventions[currency]
            if security_type and security_type in curr_data:
                return curr_data[security_type]
            elif 'securities' in curr_data:
                return curr_data['securities']
    
    # Default to T+2 if nothing found
    return 2

# Backward compatibility functions for legacy code
def load_yaml_config(config_name):
    """
    Legacy function to load a specific configuration by name.
    Maps old config file names to the new combined structure.
    """
    mapping = {
        'config/app_config.yaml': get_app_config,
        'config/spread_files.yaml': lambda: {'spread_files': get_spread_files()},
        'config/metric_file_map.yaml': lambda: {'metrics': get_metric_file_map()},
        'config/data_extender_settings.yaml': get_data_extender_settings,
        'config/file_delivery.yaml': lambda: {'monitors': get_file_delivery_monitors()},
        'maxmin_thresholds.yaml': get_maxmin_thresholds,
        'config/attribution_columns.yaml': get_attribution_columns,
        'config/date_patterns.yaml': lambda: {'date_patterns': get_date_patterns()},
        'config/field_aliases.yaml': get_field_aliases,
        'comparison_config.yaml': get_comparison_config,
        'config/settlement_conventions.yaml': get_settlement_conventions
    }
    
    if config_name in mapping:
        return mapping[config_name]()
    else:
        logger.warning(f"Unknown config name: {config_name}")
        return {}

def reload_settings():
    """Force reload of settings from disk."""
    global _settings_cache, _cache_mtime
    _settings_cache = None
    _cache_mtime = None
    logger.info("Settings cache cleared, will reload on next access")