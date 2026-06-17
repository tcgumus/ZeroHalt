# KUKA KR-360 Bakım Kılavuzu — Bölüm 7.3: Servo Aktarma Organları (s. 142–149)

## Arıza Kodu F-7412 — Servo Motor Tork Sapması (Eksen 3)

**Belirti:** Tork sapması yalnızca yüksek hız profillerinde tetiklenir; motor akım
imzası dişli geçiş frekansında bozulma gösterir.

**Kök neden:** Eksen 3 servo aktarma organında redüktör dişli aşınması. Motor akım
spektrumunda dişli geçiş frekansında yan bantlar oluşur.

**Teşhis kontrol listesi:**
- Tork sapması eşiği %8'dir; aşımda redüktörü değerlendir.
- Motor akım spektrum analizi yap (yan bant = dişli hasarı göstergesi).
- Geçmiş kayıtlarda aynı redüktörde arıza var mı kontrol et.

**Onarım prosedürü:**
1. Robotu güvenli pozisyona al, enerjiyi kilitle-etiketle (LOTO).
2. Eksen 3 redüktör ünitesini (SRV-KR360-A3) sök.
3. Yeni redüktörü monte et, tork kalibrasyonu uygula.
4. Yüksek hız profilinde test çevrimi yap, tork sapmasını doğrula (< %8).

**İlgili parça:** SRV-KR360-A3 (Redüktör Ünitesi, Eksen 3).
