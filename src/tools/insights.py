"""Önleyici bakım / öğrenme araçları (UC-06).

Geçmiş bakım kayıtlarından tekrar eden arızaları, çapraz-varyant parça açığı
riskini ve proaktif uyarıları çıkarır. Tümü saf Python + datasource okumasıyla
çalışır (Bedrock gerektirmez); online modda model de bu araçları çağırabilir.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Optional

import datasource
from src import policy

# Risk seviyesi sıralama anahtarı (panelde önce yüksek).
_RISK_RANK = {"yüksek": 0, "orta": 1, "düşük": 2}


def _mean_interval_days(dates: list[str]) -> Optional[float]:
    """Ardışık tarihler arası ortalama gün farkı (MTBF). Tek tarih → None."""
    parsed = sorted(datetime.strptime(d, "%Y-%m-%d") for d in dates if d)
    if len(parsed) < 2:
        return None
    diffs = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
    return round(sum(diffs) / len(diffs), 1)


def detect_recurring_faults(min_occurrences: int = 2) -> list[dict[str, Any]]:
    """Tekrar eden arızaları (aynı fault_code ≥ min_occurrences) tespit eder.

    Returns:
        [{fault_code, occurrences, machines[], repeated_machine, dates[],
          mtbf_days, last_root_cause, part_used, severity}]
    """
    out: list[dict[str, Any]] = []
    for g in datasource.get_fault_frequency():
        if g["occurrences"] < min_occurrences:
            continue
        machine_counts = Counter(g["machines"])
        repeated_machine = next(
            (m for m, c in machine_counts.most_common() if c >= 2), None
        )
        out.append(
            {
                "fault_code": g["fault_code"],
                "occurrences": g["occurrences"],
                "machines": sorted(set(g["machines"])),
                "repeated_machine": repeated_machine,
                "dates": sorted(g["dates"]),
                "mtbf_days": _mean_interval_days(g["dates"]),
                "last_root_cause": g["root_causes"][-1] if g["root_causes"] else "",
                "part_used": g["parts"][-1] if g["parts"] else None,
                # Aynı makinede tekrar daha kritiktir.
                "severity": "yüksek" if repeated_machine else "orta",
            }
        )
    return out


def predict_part_shortage() -> list[dict[str, Any]]:
    """Çapraz-varyant parça açığı riski.

    Parça N makinede (used_in_variants) ortak kullanılıyor + geçmiş arıza
    sayısı → öngörülen talep vs eldeki stok. Yalnızca riskli parçalar döner.

    Returns (risk + açık büyüklüğüne göre sıralı):
        [{part_code, name, on_hand, safety_stock, variant_count, variants[],
          fault_count, predicted_demand, gap, is_recurring, shortage_risk,
          recommended_qty, recommendation}]
    """
    history = datasource.get_all_maintenance_history()
    part_fault = Counter(r["part_used"] for r in history if r["part_used"])
    recurring_parts = {
        p
        for g in datasource.get_fault_frequency()
        if g["occurrences"] >= 2
        for p in g["parts"]
    }

    out: list[dict[str, Any]] = []
    for part in datasource.list_all_parts():
        code = part["part_code"]
        variants = part["used_in_variants"]
        variant_count = len(variants)
        fault_count = int(part_fault.get(code, 0))
        on_hand = part["on_hand"]
        safety = part["safety_stock"]

        predicted_demand = fault_count
        gap = predicted_demand + safety - on_hand
        below_safety = on_hand < safety
        if gap <= 0 and not below_safety:
            continue  # riskli değil

        is_recurring = code in recurring_parts
        if below_safety and (variant_count >= 2 or is_recurring):
            risk = "yüksek"
        elif below_safety:
            risk = "orta"
        else:
            risk = "düşük"

        suggestion = policy.suggest_order_quantity(
            code, datasource.count_open_demand(code)
        )
        rec_qty = suggestion["suggested_qty"]
        variant_txt = ", ".join(variants) if variants else "tek hat"
        recommendation = (
            f"{code} ({part['name']}) {variant_count} makinede ortak ({variant_txt}); "
            f"eldeki {on_hand}/{safety}"
            + (" — emniyet stoğu ALTINDA" if below_safety else "")
            + f", geçmişte {fault_count} arıza"
            + (" (tekrar eden)" if is_recurring else "")
            + f". Çapraz-varyant açık riski: {risk}. Önerilen sipariş: {rec_qty} adet."
        )

        out.append(
            {
                "part_code": code,
                "name": part["name"],
                "on_hand": on_hand,
                "safety_stock": safety,
                "variant_count": variant_count,
                "variants": variants,
                "fault_count": fault_count,
                "predicted_demand": predicted_demand,
                "gap": gap,
                "is_recurring": is_recurring,
                "shortage_risk": risk,
                "recommended_qty": rec_qty,
                "recommendation": recommendation,
            }
        )

    out.sort(key=lambda s: (_RISK_RANK.get(s["shortage_risk"], 9), -s["gap"]))
    return out


def preventive_insights() -> dict[str, Any]:
    """UC-06 birleşik çıktı: tekrar eden arızalar + parça açığı + proaktif uyarılar.

    Returns:
        {recurring_faults: [...], part_shortages: [...],
         alerts: [{level, title, detail, machine_id?, part_code?, fault_code?}]}
    """
    recurring = detect_recurring_faults()
    shortages = predict_part_shortage()
    alerts: list[dict[str, Any]] = []

    # 1) Aynı makinede tekrar eden arıza → kritik önleyici uyarı.
    for f in recurring:
        if not f["repeated_machine"]:
            continue
        mtbf = f["mtbf_days"]
        mtbf_txt = f"~{mtbf:.0f} gün" if mtbf is not None else "bilinmiyor"
        alerts.append(
            {
                "level": "kritik",
                "title": f"{f['repeated_machine']} · {f['fault_code']} tekrarlıyor",
                "detail": (
                    f"{f['repeated_machine']} makinesinde {f['fault_code']} arızası "
                    f"{f['occurrences']} kez görüldü (MTBF {mtbf_txt}). Son kök neden: "
                    f"{f['last_root_cause']} Kalıcı çözüm için önleyici kontrol önerilir."
                ),
                "machine_id": f["repeated_machine"],
                "fault_code": f["fault_code"],
                "part_code": f["part_used"],
            }
        )

    # 2) Yüksek riskli çapraz-varyant parça açığı → kritik/uyarı.
    for s in shortages:
        if s["shortage_risk"] != "yüksek":
            continue
        alerts.append(
            {
                "level": "kritik" if s["is_recurring"] else "uyari",
                "title": f"{s['part_code']} · çapraz-varyant stok açığı riski",
                "detail": s["recommendation"],
                "part_code": s["part_code"],
            }
        )

    # Kritik uyarılar önce.
    alerts.sort(key=lambda a: 0 if a["level"] == "kritik" else 1)
    return {
        "recurring_faults": recurring,
        "part_shortages": shortages,
        "alerts": alerts,
    }
