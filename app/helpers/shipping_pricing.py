"""Shipping estimates based on region/province/city tiers."""
from __future__ import annotations

from typing import Any

from helpers.marketplace_settings import get_float_setting


def _norm(val: Any) -> str:
    return str(val or "").strip().lower()


def estimate_shipping_for_seller_group(
    *,
    group_subtotal: float,
    buyer_address: dict[str, Any] | None,
    seller_geo: dict[str, Any] | None,
) -> tuple[float, str]:
    """
    Returns (fee, reason_label).
    Free shipping when group_subtotal >= configured threshold.
    """
    threshold = get_float_setting("shipping_free_threshold", 2000.0)
    if group_subtotal >= threshold or group_subtotal <= 0:
        return 0.0, "free_threshold"

    br = _norm((buyer_address or {}).get("region"))
    bp = _norm((buyer_address or {}).get("province"))
    bc = _norm((buyer_address or {}).get("city_municipality"))

    sr = _norm((seller_geo or {}).get("region"))
    sp = _norm((seller_geo or {}).get("province"))
    sc = _norm((seller_geo or {}).get("city"))

    if br and sr and br == sr and bp and sp and bp == sp and bc and sc and bc == sc:
        fee = get_float_setting("shipping_same_city", 49.0)
        return round(fee, 2), "tier_same_city"
    if br and sr and br == sr and bp and sp and bp == sp:
        fee = get_float_setting("shipping_same_province", 65.0)
        return round(fee, 2), "tier_same_province"
    if br and sr and br == sr:
        fee = get_float_setting("shipping_same_region", 79.0)
        return round(fee, 2), "tier_same_region"

    fee = get_float_setting("shipping_cross_region", 99.0)
    return round(fee, 2), "tier_cross_region"
