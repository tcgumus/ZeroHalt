"""İnsan onayı / sınır kontrolleri.

Temel ilke: Kritik kararlar (sipariş onayı) HER ZAMAN insana bırakılır. Ajan
taslak üretir; onay/red ayrı bir adımda (CLI/web'de kullanıcı) ele alınır.
"""
from __future__ import annotations

import math
from typing import Any

import config


def requires_manager_approval(est_cost: float) -> bool:
    """Eşik üstü tutarlı siparişlerde yönetici onayı bayrağını zorlar."""
    return est_cost >= config.ORDER_APPROVAL_THRESHOLD


def suggest_order_quantity(part_code: str, open_demand: int = 0) -> dict[str, Any]:
    """Tedarik süresi + açık talep + emniyet stoğuna göre şeffaf sipariş miktarı önerir.

    Formül:
        hedef = emniyet_stoğu + ceil(günlük_tüketim × tedarik_süresi) + açık_talep
        önerilen = max(0, hedef − eldeki)

    Returns:
        {part_code, found, on_hand, safety_stock, lead_time_days, daily_usage,
         lead_time_consumption, open_demand, target, suggested_qty, rationale}
    """
    import datasource

    part = datasource.get_part(part_code)
    if part is None:
        return {
            "part_code": part_code,
            "found": False,
            "suggested_qty": 0,
            "rationale": "Parça bulunamadı; miktar hesaplanamadı.",
        }

    usage = datasource.get_part_usage_rate(part_code)
    daily_usage = usage["daily_usage"]
    lead = part["lead_time_days"]
    on_hand = part["on_hand"]
    safety = part["safety_stock"]

    lead_time_consumption = math.ceil(daily_usage * lead)
    target = safety + lead_time_consumption + open_demand
    suggested = max(0, target - on_hand)

    rationale = (
        f"Hedef stok = emniyet stoğu ({safety}) + tedarik süresi tüketimi "
        f"({lead_time_consumption}; {lead} gün × {daily_usage:.3f} adet/gün) + "
        f"açık talep ({open_demand}) = {target}. Eldeki {on_hand} → "
        f"önerilen sipariş = max(0, {target} − {on_hand}) = {suggested} adet."
    )

    return {
        "part_code": part_code,
        "found": True,
        "on_hand": on_hand,
        "safety_stock": safety,
        "lead_time_days": lead,
        "daily_usage": daily_usage,
        "lead_time_consumption": lead_time_consumption,
        "open_demand": open_demand,
        "target": target,
        "suggested_qty": suggested,
        "rationale": rationale,
    }


def is_order_blocked_for_agent(action: str) -> bool:
    """Ajanın kendi başına TAMAMLAYAMAYACAĞI eylemler.

    Sipariş onayı ajan tarafından yapılamaz; yalnızca taslak üretilebilir.
    """
    return action in {"approve_order", "place_order", "confirm_order"}


def approval_banner(order: dict[str, Any]) -> str:
    """Sipariş taslağı için insan onayı uyarı metni (Türkçe)."""
    base = (
        f"⚠️ İNSAN ONAYI GEREKLİ — Taslak {order.get('draft_id')}: "
        f"{order.get('part_code')} × {order.get('quantity')} adet, "
        f"tahmini {order.get('est_cost')} TL. Durum: {order.get('status')}."
    )
    if order.get("requires_manager_approval"):
        base += (
            f" Tutar {config.ORDER_APPROVAL_THRESHOLD} TL eşiğinin üzerinde — "
            "YÖNETİCİ onayı şart."
        )
    return base


def decide(draft_id: str, approved: bool, approver: str) -> dict[str, Any]:
    """İnsan onay/red kararını uygular (datasource üzerinden kalıcılaştırır)."""
    import datasource

    return datasource.decide_order(draft_id, approved, approver)
