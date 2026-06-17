"""create_work_order tool — iş emri oluşturur."""
from __future__ import annotations

from typing import Any

import datasource


def create_work_order(
    fault_id: str,
    root_cause: str,
    steps: list[str],
    part_code: str,
    technician: str,
) -> dict[str, Any]:
    """Teşhis sonrası onarım iş emri oluşturur.

    Returns:
        {work_order_id, fault_id, root_cause, steps, part_code, technician,
         status, created_at}
    """
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.split("\n") if s.strip()]
    wo = datasource.save_work_order(
        fault_id=fault_id,
        root_cause=root_cause,
        steps=list(steps),
        part_code=part_code,
        technician=technician,
    )
    return wo
