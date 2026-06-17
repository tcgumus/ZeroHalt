# OBPYS — AWS-Ready Alt Yapı Yol Haritası

## Bağlam (neden bu çalışma)

OBPYS, bir makine arızalandığında otonom devreye giren tek-ajanlı (Bedrock `converse` tool-use) bir bakım asistanı. Şu an `OFFLINE_MODE=True` ve RAG stub — **AWS henüz yok, sonra verilecek**. Hedef ikili:

1. **Demo'yu kazandır:** Yarışmada birincilik için use-case kapsamını tamamla. Belgedeki 7 UC'den UC-01/03/05 tam, ama **UC-06 (öğrenme + önleyici bakım) hiç yok** (en büyük diferansiyel), **UC-04 sipariş miktarı sabit**, **UC-07 raporlama sahte (hardcoded duruş)**.
2. **AWS-ready ol:** Online/Bedrock/KB/multimodal kod yolları yazılmış ama hiç çalıştırılmamış → bayrak çevrilince ilk denemede patlama riski yüksek. Bunları AWS olmadan denetleyip düzelt ve botocore Stubber ile test et.

**Kararlar:** UC-07 → gerçek şema (incidents'a `resolved_at` + `downtime_hours`). Sıra → **önce özellikler (A), sonra AWS-readiness (B)**.

**İlkeler:** Tüm çıktı/metin Türkçe. LangChain yok, sade boto3. Tüm veri erişimi `datasource.py` üzerinden. Tool'lar JSON-serileştirilebilir döner. Mevcut 14 test kırılmaz; her görev kendi testini ekler.

---

## FAZ A — Offline çalışan, online-ready özellikler

### A1 · UC-04 Dinamik Sipariş Miktarı
Sipariş adedini sabit `recommended_qty` yerine şeffaf formülle hesapla.
- `src/policy.py` → `suggest_order_quantity(part_code, open_demand=0)`. Formül: `target = safety_stock + ceil(daily_usage*lead_time_days) + open_demand; suggested = max(0, target - on_hand)`.
- `datasource.py` → `get_part_usage_rate(part_code)`, `count_open_demand(part_code)`.
- `src/tools/orders.py` → `create_order_draft(part_code, quantity=None)`; None ise hesapla, `suggested` + `rationale` ekle (geriye uyumlu).
- `src/tools/__init__.py` → spec'te `quantity` required değil.
- `src/agent.py` → `_run_offline` hesaplanan miktar + `_build_summary` gerekçe satırı.
- **Kabul:** `suggest_order_quantity('HYD-4520-B',1)` → `suggested_qty>0` + Türkçe gerekçe; `python app.py E-2208` sabit 12 değil; `pytest tests/test_tools.py` yeşil.

### A2 · UC-06 Öğrenme + Önleyici Bakım (EN ÖNEMLİ)
- `src/tools/insights.py` (YENİ) → `detect_recurring_faults`, `predict_part_shortage`, `preventive_insights` (`{recurring_faults, part_shortages, alerts}`).
- `datasource.py` → `get_all_maintenance_history`, `get_fault_frequency`, `list_all_parts`.
- `src/tools/__init__.py` → 3 fonksiyon dispatch + `preventive_insights` TOOL_SPECS.
- `web/server.py` → `/api/preventive`; `index.html` → "Önleyici Uyarılar" bölümü; `app.js` → `loadPreventive` + render'lar.
- **Kabul:** `preventive_insights()` → M-1190/E-2208/F-7412 `occurrences>=2` + sayısal `mtbf_days`; HYD-4520-B `variant_count==3`, `shortage_risk=="yüksek"`; `/api/preventive` 200; panel dolu.

### A3 · UC-07 Gerçek Raporlama (gerçek şema)
- `data/incidents.csv` → `resolved_at`, `downtime_hours` kolonları.
- `datasource.init_schema` + `seed_db.py` → yeni kolonlar.
- `datasource.py` → `compute_kpis()` (MTBF/MTTR/çözüm oranı/duruş), `weekly_downtime()`.
- `web/server.py overview()` → gerçek veri (eski anahtarlar korunur); `app.js` → MTBF/MTTR/Çözüm Oranı kartları.
- **Kabul:** `python seed_db.py` ok; `compute_kpis()`/`weekly_downtime()` sayısal + dinamik; panel gerçek KPI.

> **KONTROL NOKTASI 1:** `pytest -q` yeşil + `python app.py --web` insan incelemesi. Sonra Faz B.

---

## FAZ B — AWS-readiness (Stubber ile AWS'siz doğrulanır)

- **B0** · `BedrockClient` enjekte edilebilir `runtime_client`; `_strip_thinking`, `_detect_image_format` helper'ları; Stubber test iskeleti.
- **B1** · Converse döngüsü: RISK2 `toolResult.status`; RISK5 greedy (`temp=0.0`+`topK=1`); RISK3 sözleşme fallback; RISK1 thinking temizleme; RISK8 boş özet fallback.
- **B2** · KB: RISK7 dayanıklı `_query_real` ayrıştırma; RISK6 görünür hata/degraded.
- **B3** · Multimodal: RISK4 `_detect_image_format` ile dinamik format.
- **B4** · `app.js` defansif online sözleşme korumaları.
- **B5** · `src/preflight.py --dry-run`; `.env.example` kademeli bayrak notu.
- **Kabul (Stubber):** converse status/greedy doğru; thinking sızmaz; görüntü formatı baytla eşleşir; retrieve KeyError yok; 429 backoff; preflight geçerli JSON.

> **KONTROL NOKTASI 2:** `pytest -q` (mevcut + Stubber) yeşil; preflight doğrulanır.

---

## Bağımlılık Sırası
A1 → A2 → A3 → **KN1** → B0 → (B1, B2, B3) → B4 → B5 → **KN2**.

## Uçtan Uca Doğrulama
1. `python seed_db.py` 2. `python -m pytest -q` 3. `python app.py E-2208` 4. `python app.py --web` 5. `python -m src.preflight --dry-run`
