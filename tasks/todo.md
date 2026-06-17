# OBPYS — Görev Listesi (todo)

Plan: `tasks/plan.md`. Sıra: A1 → A2 → A3 → [KN1] → B0 → B1/B2/B3 → B4 → B5 → [KN2].

## FAZ A — Offline çalışan, online-ready özellikler

### A1 · UC-04 Dinamik Sipariş Miktarı
- [ ] `datasource.get_part_usage_rate(part_code)` + `count_open_demand(part_code)`
- [ ] `policy.suggest_order_quantity(part_code, open_demand=0)` (şeffaf formül + Türkçe gerekçe)
- [ ] `orders.create_order_draft(part_code, quantity=None)` — None ise hesapla, `suggested`+`rationale`
- [ ] `tools/__init__.py` spec: `quantity` required değil
- [ ] `agent._run_offline` hesaplanan miktar + `_build_summary` gerekçe satırı
- [ ] Test: `tests/test_tools.py::test_create_order_draft_auto_quantity`
- [ ] Doğrula: `python app.py E-2208`

### A2 · UC-06 Öğrenme + Önleyici Bakım
- [ ] `datasource.get_all_maintenance_history` + `get_fault_frequency` + `list_all_parts`
- [ ] `src/tools/insights.py`: `detect_recurring_faults`, `predict_part_shortage`, `preventive_insights`
- [ ] `tools/__init__.py`: dispatch + `preventive_insights` TOOL_SPECS
- [ ] `web/server.py`: `/api/preventive`
- [ ] `index.html`: "Önleyici Uyarılar" bölümü + nav
- [ ] `app.js`: `loadPreventive` + render'lar
- [ ] Test: `tests/test_insights.py`
- [ ] Doğrula: `/api/preventive` + panel

### A3 · UC-07 Gerçek Raporlama
- [ ] `data/incidents.csv`: `resolved_at` + `downtime_hours`
- [ ] `datasource.init_schema` + `seed_db.py`: yeni kolonlar
- [ ] `datasource.compute_kpis` + `weekly_downtime`
- [ ] `web/server.py overview()`: gerçek veri (eski anahtarlar korunur)
- [ ] `app.js`: MTBF/MTTR/Çözüm Oranı kartları
- [ ] Test: `tests/test_reporting.py`
- [ ] Doğrula: `python seed_db.py` + panel

- [ ] **KONTROL NOKTASI 1** — `pytest -q` yeşil + panel insan incelemesi

## FAZ B — AWS-readiness
- [ ] B0 · enjekte edilebilir `runtime_client` + `_strip_thinking` + `_detect_image_format` + Stubber iskeleti
- [ ] B1 · converse: status / greedy(topK) / sözleşme fallback / thinking / boş özet
- [ ] B2 · KB: dayanıklı `_query_real` + görünür hata
- [ ] B3 · multimodal: dinamik görüntü formatı
- [ ] B4 · `app.js` defansif online korumaları
- [ ] B5 · `src/preflight.py --dry-run` + `.env.example` kademeli bayrak notu
- [ ] Stubber testleri: `tests/test_bedrock_payloads.py`, `test_online_agent.py`, `test_image_format.py`, `test_preflight.py`
- [ ] **KONTROL NOKTASI 2** — `pytest -q` (mevcut + Stubber) yeşil + preflight doğrulanır
