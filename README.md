
## 🏆 This project won 1st place at the hackathon.
## 🏆 Bu proje hackathonda birincilik ödülü kazandı.

#
#
#
        

# ZeroHalt — Otonom Bakım ve Parça Yönetim Sistemi


Üretim hattında bir makine arızalandığında **otonom devreye giren bir yapay zekâ
ajanı**. Görevi: arızanın kök nedenini bulmak, çözüm adımlarını çıkarmak, gereken
yedek parçayı tanımlamak, stok durumunu kontrol etmek, muadil önermek, **sipariş
taslağı** hazırlamak ve **iş emri** oluşturmak.

> **Kritik kararlar (sipariş onayı) HER ZAMAN insana bırakılır.** Ajan bunları kendi
> başına tamamlamaz; yalnızca onay bekleyen taslak üretir.

Hedef platform: AWS (Amazon Bedrock + Bedrock AgentCore). Dil: Python 3.11+.
Arayüz: **ZeroHalt Bakım Paneli** (web).

---

## Mimari

- **Tek ajan, tek model.** Reasoning'i tek bir model (Bedrock `converse` üzerinden)
  yapar. Ayrı supervisor yok; orkestrasyonu modelin **tool-use** döngüsü yürütür.
- **Özellikler = tool.** Her yetenek bağımsız bir fonksiyon/tool'dur. Model hangi
  tool'u ne zaman çağıracağına karar verir.
- **RAG** Bedrock Knowledge Base ile (`retrieve`). Kota/sync hazır olana kadar
  `query_knowledge_base` **stub** çalışır (`USE_REAL_KB=false`).
- **Görüntüden parça tanıma** ayrı model değildir; aynı multimodal model fotoğrafı okur.
- **Veri katmanı tek noktadan:** tüm tool'lar veriye yalnızca `datasource.py`
  üzerinden erişir (arkada SQLite; ileride MES/ERP/CMMS ile değişir).
- **İki çalışma modu, aynı sonuç:**
  - `OFFLINE_MODE=true` → Bedrock'suz deterministik akış (demo/CI; varsayılan).
  - `OFFLINE_MODE=false` → boto3 Bedrock `converse` tool-use döngüsü (AWS kimliği gerekir).

```
.
├─ config.py            # bölge, model id, KB id, eşikler (env'den)
├─ datasource.py        # mock veri katmanı (SQLite) — TEK erişim noktası
├─ seed_db.py           # data/*.csv -> SQLite tohumlama
├─ app.py               # CLI demo + web başlatıcı
├─ data/                # parts/substitutes/maintenance_history/incidents .csv,
│                       # fault_signatures.json, manuals/ (KB kaynağı)
├─ src/
│  ├─ bedrock_client.py # converse + KB retrieve + 429 backoff
│  ├─ prompts.py        # Türkçe sistem promptu (oyun kitabı)
│  ├─ agent.py          # tool-use orkestrasyon döngüsü + offline akış
│  ├─ policy.py         # insan onayı / sınır kontrolleri
│  └─ tools/            # stock, parts, substitutes, orders, work_orders, knowledge
├─ web/                 # Flask sunucu + FNSS paneli (HTML/CSS/JS)
└─ tests/
```

## Tool'lar

| Tool | İmza |
|------|------|
| `stock_lookup` | `(part_code) -> {on_hand, safety_stock, lead_time_days, below_safety}` |
| `part_info` | `(part_code) -> {specs, used_in_variants, ...}` |
| `identify_part` | `(image_b64/hint) -> {part_code, name, confidence}` (multimodal) |
| `find_substitutes` | `(part_code) -> [{substitute_code, on_hand, compatibility_note, approved}]` |
| `create_order_draft` | `(part_code, quantity) -> {draft_id, est_cost, status:"pending_approval"}` |
| `create_work_order` | `(fault_id, root_cause, steps, part_code, technician) -> {work_order_id, ...}` |
| `query_knowledge_base` | `(query) -> {answer, sources}` (Bedrock KB / stub) |

---

## Kurulum ve Çalıştırma

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # değerleri doldurun (Windows; Linux/Mac: cp)
python seed_db.py                 # SQLite veritabanını CSV'lerden oluştur
```

### CLI demo (kabul kriteri senaryosu)

```bash
python app.py                     # varsayılan arıza E-2208 — uçtan uca zincir
python app.py F-7412              # başka bir arıza kodu
python app.py --list              # aktif arıza kuyruğu
```

### Web paneli (FNSS)

```bash
python app.py --web               # http://127.0.0.1:5000
```

Panelde: bir arıza seçin → **Ajanı Çalıştır** → kök neden (+güven), parça/stok,
muadil, **onay bekleyen sipariş taslağı** (Onayla/Reddet butonları), iş emri ve
ajanın tool-use zinciri görünür. Sağ alttaki **Asistan** ile sohbet edebilirsiniz.

### Testler

```bash
pytest                            # 14 test — tool katmanı + uçtan uca akış + policy
```

---

## Gerçek Bedrock'a geçiş

1. AWS kimliğini sağlayın (`aws configure` veya `AWS_*` env / SSO). Secret koda yazılmaz.
2. `.env` içinde `OFFLINE_MODE=false` yapın ve `BEDROCK_MODEL_ID`'yi bölgede
   erişilebilir tam ID ile doğrulayın (Bedrock Playground).
3. Knowledge Base sync tamamlanınca `USE_REAL_KB=true` yapın — stub ile gerçek
   `retrieve` **aynı imzayı** döndürür, kod değişmez.
4. Tüm Bedrock çağrılarında 429 ThrottlingException için exponential backoff aktiftir.

## Ortam Değerleri (mevcut)

- `AWS_REGION=eu-central-1` · `KNOWLEDGE_BASE_ID=LYKPLY3GMD` · `DATA_SOURCE_ID=E0GIBVCAQM`
- S3: `s3://kb-dosyasi` · Embedding: Titan Text Embeddings v2 (1024) / S3 Vectors
- Model (başlangıç): Amazon Nova (multimodal + tool-use). Claude'a geçiş yalnızca
  `BEDROCK_MODEL_ID` değiştirir; kod aynı kalır.

## Durum notları

- **RAG geçici olarak STUB:** KB oluşturuldu ama hesap kotası (429) nedeniyle henüz
  sync edilemedi. `query_knowledge_base` örnek kılavuz içeriğinden temsili cevap
  döndürür. Sync sonrası `USE_REAL_KB=true`.
- **AgentCore** (Runtime/Memory/Gateway/Policy) deploy'u en sona bırakıldı; önce
  lokalde çalışan ajan çıkarıldı.
