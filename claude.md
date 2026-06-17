# CLAUDE.md — ZeroHalt · Otonom Bakım ve Parça Yönetim Sistemi

## 1. Proje Amacı
Üretim hattında bir makine arızalandığında otonom devreye giren bir AI ajanı.
Görevi: arızanın kök nedenini bulmak, çözüm adımlarını çıkarmak, gereken yedek
parçayı tanımlamak, stok durumunu kontrol etmek, muadil önermek, sipariş taslağı
hazırlamak ve iş emri oluşturmak. Kritik kararlar (sipariş onayı) HER ZAMAN insana
bırakılır — ajan bunları kendi başına tamamlamaz.

Hedef platform: AWS (Amazon Bedrock + Bedrock AgentCore). Geliştirme dili: Python.

## 2. Mimari (önemli — buna uy)
- **Tek ajan, tek model.** Reasoning'i tek bir Claude modeli (Bedrock üzerinden) yapar.
  Ayrı bir "supervisor" bileşeni YOK; orkestrasyonu modelin tool-use'u yürütür.
- **Özellikler = tool.** Her yetenek (stok, parça, muadil, sipariş, iş emri, RAG)
  bağımsız bir fonksiyon/tool olarak tanımlanır. Model hangi tool'u ne zaman
  çağıracağına karar verir.
- **RAG** Bedrock Knowledge Base ile yapılır (vektör DB'yi elle kurma).
- **Görüntüden parça tanıma** ayrı model değildir; aynı multimodal Claude modeli
  fotoğrafı okur.
- **AgentCore** (Runtime/Memory/Gateway/Policy) production/deploy aşaması içindir.
  Önce lokalde boto3 ile çalıştır, sonra AgentCore'a taşı.

KESİNLİKLE YAPMA: LangChain veya gereksiz framework ekleme. Sade tut: boto3 Bedrock
`converse` tool-use döngüsü (tercih) ya da Strands Agents SDK. Çoklu model kullanma.

## 3. Teknoloji Yığını
- Python 3.11+
- boto3 (Bedrock Runtime `converse` API + Knowledge Base retrieve)
- (opsiyonel) strands-agents SDK — converse döngüsünü sarmalamak istersen
- Bölge: eu-central-1 (Frankfurt)
- Model: [TODO: bölgede erişilebilir Claude model ID'sini doğrula ve config'e koy]
- pandas (mock veri okuma), python-dotenv (config)

## 4. Repo Yapısı (bunu oluştur)
.
├─ CLAUDE.md
├─ README.md
├─ requirements.txt
├─ .env.example
├─ config.py                 # bölge, model id, KB id, eşikler (env'den okur)
├─ data/
│  ├─ parts.csv
│  ├─ substitutes.csv
│  ├─ maintenance_history.csv
│  ├─ manuals/               # KB'ye yüklenecek PDF kılavuzlar
│  └─ part_images/           # örnek parça fotoğrafları
├─ src/
│  ├─ bedrock_client.py      # Bedrock converse + KB retrieve sarmalayıcı
│  ├─ prompts.py             # sistem promptu (oyun kitabı)
│  ├─ agent.py               # ajan + tool-use orkestrasyon döngüsü
│  ├─ policy.py              # insan onayı / sınır kontrolleri
│  └─ tools/
│     ├─ init.py         # TOOL_SPECS listesi + dispatch
│     ├─ stock.py            # stock_lookup
│     ├─ parts.py            # part_info, identify_part (multimodal)
│     ├─ substitutes.py      # find_substitutes
│     ├─ orders.py           # create_order_draft
│     ├─ work_orders.py      # create_work_order
│     └─ knowledge.py        # query_knowledge_base (RAG)
├─ datasource.py             # mock veri katmanı (sonra gerçek MES/ERP ile değişir)
├─ app.py                    # basit CLI/demo akışı
└─ tests/

## 5. Veri Şemaları (mock CSV üret + örnek kayıtlarla doldur)
- **parts.csv**: `part_code, name, category, specs, on_hand, safety_stock,
  unit_cost, lead_time_days, used_in_variants`
- **substitutes.csv**: `part_code, substitute_code, compatibility_note, approved(bool)`
- **maintenance_history.csv**: `record_id, machine_id, date, fault_code, root_cause,
  part_used, resolution`
- **manuals/**: arıza kodları ve onarım prosedürlerini içeren temsili PDF'ler (KB için)

Önemli: tüm tool'lar veriye DOĞRUDAN değil `datasource.py` üzerinden erişsin.
Böylece ileride mock CSV → gerçek MES/ERP/CMMS bağlantısına geçmek tek noktadan olur.

## 6. Tool Tanımları (imza + girdi/çıktı)
Hepsi JSON-serileştirilebilir dönsün; tool spec'leri Bedrock `toolConfig` formatında
`src/tools/__init__.py` içinde toplansın.

- `stock_lookup(part_code) -> {part_code, name, on_hand, safety_stock, lead_time_days}`
- `part_info(part_code) -> {part_code, name, specs, used_in_variants}`
- `identify_part(image_bytes) -> {part_code, name, confidence}`  # multimodal model
- `find_substitutes(part_code) -> [{substitute_code, name, on_hand, compatibility_note}]`
- `create_order_draft(part_code, quantity) -> {draft_id, part_code, quantity,
   est_cost, status:"pending_approval"}`
- `create_work_order(fault_id, root_cause, steps[], part_code, technician)
   -> {work_order_id, ...}`
- `query_knowledge_base(query) -> {answer, sources[]}`  # Bedrock KB retrieve

## 7. Ajan Davranışı / Sistem Promptu (oyun kitabı)
`src/prompts.py` içinde, ajanın TÜRKÇE yanıt veren sistem promptunu yaz. Akış:
1. Gelen arızayı yorumla, ilgili ekipmanı belirle.
2. `query_knowledge_base` ve geçmiş kayıtlarla kök nedeni güven düzeyiyle çıkar.
3. Gereken parçayı belirle (gerekirse `identify_part`), `part_info` + `stock_lookup`.
4. Stok < safety_stock ise `find_substitutes` çağır.
5. Sipariş gerekiyorsa `create_order_draft` ile taslak hazırla (ASLA onaylama).
6. `create_work_order` ile iş emri oluştur.
7. Kullanıcıya net, Türkçe bir özet ver: kök neden, parça/stok durumu, önerilen aksiyon.

Prompt'ta açıkça yaz: kritik kararlar insan onayına tabidir; ajan sipariş/işlemi
kendi tamamlamaz, taslak üretir.

## 8. İnsan Onayı / Policy (`policy.py`)
- `create_order_draft` çıktısı her zaman `status="pending_approval"`.
- [TODO: onay eşiği] üstü tutarlı siparişlerde "onay gerekli" bayrağını zorla.
- Onay/red eylemi koddan ayrı bir adımda (CLI'da kullanıcı onayı) ele alınsın.

## 9. Bedrock Entegrasyonu (`bedrock_client.py`)
- `boto3.client("bedrock-runtime", region_name=...)` ile `converse` çağrısı;
  `toolConfig` ile tool'ları geç, dönüşte tool-use isteklerini çalıştır, sonucu
  geri besle (tool-use döngüsü). Döngüyü `agent.py` yönetsin.
- Multimodal: `identify_part` için görüntüyü `converse` mesajına image bloğu olarak ekle.
- RAG: `boto3.client("bedrock-agent-runtime")` ile `retrieve` / `retrieve_and_generate`,
  `knowledgeBaseId=[TODO: KB ID]`.
- Kimlik bilgisi koddan değil ortamdan gelsin (AWS profili / env). Asla secret hardcode etme.

## 10. Config (`config.py` + `.env.example`)
Şunları env'den oku: `AWS_REGION`, `BEDROCK_MODEL_ID`, `KNOWLEDGE_BASE_ID`,
`ORDER_APPROVAL_THRESHOLD`. `.env.example` dosyasını TODO açıklamalarıyla doldur.

## 11. Çalıştırma / Komutlar (README'ye de yaz)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # değerleri doldur
aws configure               # veya AWS_* env değişkenleri
python app.py               # demo akışını çalıştır
pytest                      # testler

## 12. Geliştirme İlkeleri
- Küçük, test edilebilir adımlarla ilerle; her tool'u tek başına çalışır yap.
- Type hint + docstring kullan. Fonksiyonlar kısa ve tek sorumluluklu olsun.
- Tool'lar Bedrock olmadan da (mock datasource ile) doğrudan çağrılıp test edilebilsin;
  böylece AWS kimliği gelmeden tool katmanı geliştirilebilir.
- Kullanıcıya/ajana dönen tüm metinler TÜRKÇE.
- AWS SDK imzalarını, model ID'lerini ve AgentCore API'lerini UYDURMA; emin değilsen
  açık `# TODO: dokümandan doğrula` notu bırak.
- AgentCore deploy'u en sona bırak; önce lokalde çalışan bir ajan çıkar.

## 13. Kabul Kriteri (demo senaryosu)
Tek bir arıza kodundan başlayıp: kök neden → parça/stok → muadil → sipariş taslağı
(onay bekleyen) → iş emri zincirini, mock veriyle uçtan uca, Türkçe çıktı vererek
tamamlayabilmeli. İnsan onayı adımı görünür olmalı.

## EK: Mevcut Ortam Değerleri ve Geçici Durumlar
- AWS_REGION = eu-central-1 (Frankfurt)
- KNOWLEDGE_BASE_ID = LYKPLY3GMD
- DATA_SOURCE_ID = E0GIBVCAQM
- S3 bucket = kb-dosyasi (s3://kb-dosyasi)
- BEDROCK_MODEL_ID = [Nova 2 Lite'ın tam ID'si — Playground'dan al; EU'da büyük
  olasılıkla cross-region inference profili: "eu.amazon.nova-lite-v1:0" gibi]
- Embedding = Titan Text Embeddings v2 (1024) / Vektör deposu = Amazon S3 Vectors

### ÖNEMLİ — RAG geçici olarak STUB
Knowledge Base oluşturuldu ama hesap kotası nedeniyle (429) henüz sync edilemedi.
Bu yüzden `query_knowledge_base` aracını ŞİMDİLİK stub/mock olarak yaz:
örnek kılavuz içeriğinden (TTL-101, HID-220 vb. arıza kodları) sabit/temsili cevap
döndürsün. Gerçek Bedrock `retrieve` çağrısını (KNOWLEDGE_BASE_ID ile) ayrı bir
fonksiyonda hazır tut ve `USE_REAL_KB = False` bayrağıyla kapat. Kota açılıp sync
bitince bayrağı True yapınca gerçeğe geçsin. Stub ile gerçek aynı imzayı döndürsün.

### Throttling/backoff
Hesap rate-limit'li olduğundan, tüm Bedrock çağrılarına exponential backoff'lu
retry ekle (429 ThrottlingException'da bekleyip tekrar dene).

### Model
Başlangıç modeli Amazon Nova (multimodal + tool-use). Claude'a geçilecekse sadece
BEDROCK_MODEL_ID değişir; kod aynı kalır. Parça fotoğrafı tanıma da aynı Nova
modeliyle (görüntü girişi) yapılır, ayrı model yok.

### Çalıştırma sırası önerisi
1) Önce tool'ları mock veriyle tek tek çalışır yap (Bedrock'suz test edilebilsin).
2) Sonra agent + converse tool-use döngüsünü bağla.
3) RAG'ı en son gerçeğe çevir.