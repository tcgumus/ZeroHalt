"""stock_lookup tool — parça stok durumu."""
from __future__ import annotations

from typing import Any

import datasource


def stock_lookup(part_code: str) -> dict[str, Any]:
    """Bir parçanın güncel stok durumunu döndürür.

    Returns:
        {part_code, name, on_hand, safety_stock, lead_time_days, below_safety, found}
    """
    part = datasource.get_part(part_code)
    if part is None:
        return {"part_code": part_code, "found": False, "error": "Parça bulunamadı."}
    return {
        "part_code": part["part_code"],
        "name": part["name"],
        "on_hand": part["on_hand"],
        "safety_stock": part["safety_stock"],
        "lead_time_days": part["lead_time_days"],
        "below_safety": part["on_hand"] < part["safety_stock"],
        "found": True,
    }
