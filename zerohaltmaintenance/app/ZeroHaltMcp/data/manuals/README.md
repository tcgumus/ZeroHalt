# Kılavuzlar (Knowledge Base kaynağı)

Bu klasör, Bedrock Knowledge Base'e yüklenecek temsili bakım kılavuzlarını içerir.
Gerçek dağıtımda buraya PDF kılavuzlar konur ve S3 (`s3://kb-dosyasi`) üzerinden
KB'ye sync edilir.

Kota/sync hazır olana kadar `src/tools/knowledge.py` içindeki **stub**, aşağıdaki
`.md` dosyalarındaki arıza kodu içeriğini temsili cevap olarak döndürür
(`USE_REAL_KB=false`). Sync bitince `USE_REAL_KB=true` yapılınca gerçek
`retrieve` çağrısına geçilir; imza aynıdır.

Dosyalar:
- `hidrolik_guc_unitesi.md` — E-2208, HID-220
- `servo_aktarma.md` — F-7412
- `genel_ariza_kodlari.md` — TTL-101, M-1190, P-0834, K-3321
