"""create_order_draft tool — sipariş TASLAĞI hazırlar.

ÖNEMLİ: Ajan siparişi ASLA kendi onaylamaz. Çıktı her zaman
status="pending_approval". Onay/red ayrı bir insan adımıdır (policy + CLI/web).
"""
from __future__ import annotations

from typing import Any, Optional

import datasource
from src.policy import requires_manager_approval, suggest_order_quantity


def create_order_draft(part_code: str, quantity: Optional[int] = None) -> dict[str, Any]:
    """Onay bekleyen sipariş taslağı oluşturur.

    `quantity` verilmezse ajan, tedarik süresi + açık talep + emniyet stoğundan
    miktarı şeffaf bir formülle HESAPLAR (bkz. policy.suggest_order_quantity).

    Returns:
        {draft_id, part_code, name, quantity, unit_cost, est_cost, lead_time_days,
         status, requires_manager_approval, suggested, rationale, found}
    """
    part = datasource.get_part(part_code)
    if part is None:
        return {"part_code": part_code, "found": False, "error": "Parça bulunamadı."}

    suggested = False
    rationale: Optional[str] = None
    if quantity is None:
        suggestion = suggest_order_quantity(
            part_code, datasource.count_open_demand(part_code)
        )
        quantity = suggestion["suggested_qty"]
        rationale = suggestion["rationale"]
        suggested = True

    quantity = max(1, int(quantity))
    est_cost = round(part["unit_cost"] * quantity, 2)
    needs_mgr = requires_manager_approval(est_cost)

    draft = datasource.save_order_draft(
        part_code=part_code,
        quantity=quantity,
        est_cost=est_cost,
        requires_manager_approval=needs_mgr,
    )
    return {
        "draft_id": draft["draft_id"],
        "part_code": part_code,
        "name": part["name"],
        "quantity": quantity,
        "unit_cost": part["unit_cost"],
        "est_cost": est_cost,
        "lead_time_days": part["lead_time_days"],
        "status": draft["status"],  # "pending_approval"
        "requires_manager_approval": needs_mgr,
        "suggested": suggested,
        "rationale": rationale,
        "found": True,
    }
