"""UC-07 gerçek raporlama / KPI testleri."""
from __future__ import annotations

import datasource


def test_compute_kpis_real():
    k = datasource.compute_kpis()
    for key in (
        "aktif_ariza",
        "cozulen_ariza",
        "kritik_stok",
        "bekleyen_siparis",
        "mttr_saat",
        "toplam_durus_saat",
        "cozum_orani",
        "haftalik_durus",
    ):
        assert key in k
    assert 0 <= k["cozum_orani"] <= 100
    assert k["mttr_saat"] > 0  # çözülen olaylardan ortalama çözüm süresi
    assert isinstance(k["mtbf_gun"], (int, float))


def test_weekly_downtime_not_hardcoded():
    dt = datasource.weekly_downtime()
    assert len(dt) == 7
    labels = [d[0] for d in dt]
    assert labels == ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    total = sum(d[1] for d in dt)
    assert total > 0
    # Eski sabit dizi [6.5,4.2,7.8,3.1,5.4,2.0,1.2] DEĞİL.
    assert [d[1] for d in dt] != [6.5, 4.2, 7.8, 3.1, 5.4, 2.0, 1.2]


def test_incident_has_downtime_fields():
    incidents = {i["incident_id"]: i for i in datasource.list_incidents()}
    assert "downtime_hours" in incidents["INC-0834"]
    assert incidents["INC-0834"]["resolved_at"]  # çözülen olayın çözüm zamanı var
