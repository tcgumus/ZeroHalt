"""find_substitutes tool — muadil parça önerisi."""
from __future__ import annotations

from typing import Any

import datasource


def find_substitutes(part_code: str) -> list[dict[str, Any]]:
    """Bir parça için muadilleri döndürür (önce onaylı + stoğu yüksek olanlar).

    Returns:
        [{substitute_code, name, on_hand, compatibility_note, approved}]
    """
    subs = datasource.get_substitutes(part_code)
    return [
        {
            "substitute_code": s["substitute_code"],
            "name": s["name"],
            "on_hand": s["on_hand"],
            "compatibility_note": s["compatibility_note"],
            "approved": s["approved"],
        }
        for s in subs
    ]
