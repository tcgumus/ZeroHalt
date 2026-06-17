"""UC-06 önleyici bakım / öğrenme testleri (Bedrock olmadan)."""
from __future__ import annotations

from src import tools
from src.tools.insights import (
    detect_recurring_faults,
    predict_part_shortage,
    preventive_insights,
)


def test_detect_recurring_faults_finds_repeats():
    faults = {f["fault_code"]: f for f in detect_recurring_faults()}
    # Geçmişte 2 kez görülen arızalar tespit edilmeli.
    for code in ("M-1190", "E-2208", "F-7412"):
        assert code in faults, f"{code} tekrar eden olarak bulunamadı"
        assert faults[code]["occurrences"] >= 2
        assert isinstance(faults[code]["mtbf_days"], (int, float))
    # M-1190 aynı makinede (PRES-HP2) tekrarladı.
    assert faults["M-1190"]["repeated_machine"] == "PRES-HP2"


def test_predict_part_shortage_cross_variant():
    shortages = {s["part_code"]: s for s in predict_part_shortage()}
    assert "HYD-4520-B" in shortages
    hyd = shortages["HYD-4520-B"]
    assert hyd["variant_count"] == 3
    assert hyd["shortage_risk"] == "yüksek"
    assert hyd["recommended_qty"] > 0
    # Bol stoklu parça riskli listede olmamalı.
    assert "HYD-4519-B" not in shortages


def test_preventive_insights_has_alerts():
    d = preventive_insights()
    assert d["recurring_faults"]
    assert d["part_shortages"]
    assert d["alerts"]
    # Kritik uyarılar önce sıralanır.
    assert d["alerts"][0]["level"] == "kritik"


def test_preventive_insights_dispatch():
    out = tools.dispatch("preventive_insights", {})
    assert "alerts" in out
    assert "preventive_insights" in [t["toolSpec"]["name"] for t in tools.TOOL_SPECS]
