"""Shipping estimates: geo distance when coordinates exist, otherwise region/province/city tiers."""
from __future__ import annotations

import math
from typing import Any

from helpers.marketplace_settings import get_float_setting


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _num(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def estimate_shipping_for_seller_group(
    *,
    group_subtotal: float,
    buyer_address: dict[str, Any] | None,
    seller_geo: dict[str, Any] | None,
) -> tuple[float, str]:
    """
    Returns (fee, reason_label).
    Shipping is based on seller-to-buyer locality, with optional distance pricing
    when coordinates are available.
    """
    if group_subtotal <= 0:
        return 0.0, "empty_group"

    bla = _num((buyer_address or {}).get("latitude"))
    blo = _num((buyer_address or {}).get("longitude"))
    sla = _num((seller_geo or {}).get("latitude"))
    slo = _num((seller_geo or {}).get("longitude"))

    if None not in (bla, blo, sla, slo):
        dist = _haversine_km(bla, blo, sla, slo)
        base = get_float_setting("distance_shipping_base", 39.0)
        per_km = get_float_setting("distance_shipping_per_km", 12.0)
        cap = get_float_setting("distance_shipping_max", 250.0)
        fee = min(cap, base + per_km * max(dist, 0.5))
        return round(fee, 2), f"distance_{dist:.1f}km"

    br = str((buyer_address or {}).get("region") or "")
    bp = str((buyer_address or {}).get("province") or "")
    bc = str((buyer_address or {}).get("city_municipality") or "")

    sr = str((seller_geo or {}).get("region") or "")
    sp = str((seller_geo or {}).get("province") or "")
    sc = str((seller_geo or {}).get("city") or "")

    if br and sr and br == sr and bp and sp and bp == sp and bc and sc and bc == sc:
        fee = get_float_setting("shipping_same_city", 49.0)
        return round(fee, 2), "tier_same_city"
    if br and sr and br == sr and bp and sp and bp == sp:
        fee = get_float_setting("shipping_same_province", 79.0)
        return round(fee, 2), "tier_same_province"
    if br and sr and br == sr:
        fee = get_float_setting("shipping_same_region", 109.0)
        return round(fee, 2), "tier_same_region"

    fee = get_float_setting("shipping_cross_region", 149.0)
    return round(fee, 2), "tier_cross_region"
