"""Load configurable marketplace settings from platform_settings (with safe defaults)."""
from typing import Any

from helpers.QueryHelpers import executeGet


_DEFAULTS = {
    "protection_enabled": "true",
    "protection_pct_of_subtotal": "1.5",
    "protection_fee_min": "5",
    "protection_fee_max": "199",
    "shipping_free_threshold": "2000",
    "shipping_same_city": "49",
    "shipping_same_province": "65",
    "shipping_same_region": "79",
    "shipping_cross_region": "99",
    "rider_commission_pct_of_shipping": "70",
    "rider_commission_pct_of_convenience": "25",
    "distance_shipping_base": "39",
    "distance_shipping_per_km": "12",
    "distance_shipping_max": "250",
}


def _settings_snapshot() -> dict[str, str]:
    rows = executeGet("SELECT setting_key, setting_value FROM platform_settings", ())
    if not isinstance(rows, list) or not rows:
        return dict(_DEFAULTS)
    merged = dict(_DEFAULTS)
    for row in rows:
        key = (row.get("setting_key") or "").strip()
        if key:
            merged[key] = str(row.get("setting_value") or "").strip()
    return merged


def refresh_marketplace_settings_cache():
    """Reserved for admin settings UI to force reload after updates."""
    return None


def get_setting(key: str, default: str | None = None) -> str:
    snap = _settings_snapshot()
    if key in snap and snap[key] != "":
        return snap[key]
    if default is not None:
        return default
    return _DEFAULTS.get(key, "")


def get_bool_setting(key: str, default: bool = True) -> bool:
    val = get_setting(key, "true" if default else "false").lower()
    return val in {"1", "true", "t", "yes", "y", "on"}


def get_float_setting(key: str, default: float = 0.0) -> float:
    try:
        return float(get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def compute_protection_fee(eligible_subtotal: float) -> float:
    if not get_bool_setting("protection_enabled", True):
        return 0.0
    if eligible_subtotal <= 0:
        return 0.0
    pct = get_float_setting("protection_pct_of_subtotal", 1.5) / 100.0
    fee_min = get_float_setting("protection_fee_min", 5.0)
    fee_max = get_float_setting("protection_fee_max", 199.0)
    raw = eligible_subtotal * pct
    fee = max(fee_min, min(fee_max, raw))
    return round(fee, 2)
