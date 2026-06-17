"""query_knowledge_base tool — RAG (Bedrock Knowledge Base).

ÖNEMLİ (geçici): Hesap kotası (429) nedeniyle KB henüz sync edilemedi. Bu yüzden
varsayılan olarak STUB çalışır (`USE_REAL_KB=false`) ve örnek kılavuz içeriğinden
temsili cevap döndürür. Gerçek `retrieve` çağrısı `_query_real()` içinde hazırdır;
kota açılıp sync bitince `.env`'de USE_REAL_KB=true yapılınca devreye girer.
Stub ile gerçek AYNI imzayı döndürür: {answer, sources[]}.
"""
from __future__ import annotations

import re
from typing import Any

import config

# Arıza kodu -> temsili kılavuz cevabı (stub). Manuals klasöründeki içerikle uyumlu.
_STUB_KB: dict[str, dict[str, Any]] = {
    "E-2208": {
        "answer": (
            "E-2208 (Hidrolik Güç Ünitesi Basınç Düşüşü): En olası kök neden, eksenel "
            "pistonlu pompada iç kaçaktır (piston/pabuç yüzey aşınması). Basınç düşüşü "
            "pompa çıkış hattında başlar, karter sıcaklığı artar, yağda bronz partikül "
            "görülür. İlgili parça HYD-4520-B. Onarım: LOTO, basınç tahliyesi, pompa "
            "sökümü, yeni/muadil pompa montajı (M12 tork 86 Nm), 280 bar basınç testi."
        ),
        "sources": [
            "DMG MORI NLX-2500 Servis Kılavuzu · Bölüm 4.2 — Hidrolik Güç Ünitesi, s. 87–93",
        ],
        "part": "HYD-4520-B",
    },
    "F-7412": {
        "answer": (
            "F-7412 (Servo Motor Tork Sapması, Eksen 3): Kök neden, Eksen 3 servo "
            "aktarma organında redüktör dişli aşınmasıdır. Tork sapması yalnızca yüksek "
            "hız profillerinde tetiklenir; motor akım spektrumunda dişli geçiş "
            "frekansında yan bantlar oluşur. İlgili parça SRV-KR360-A3."
        ),
        "sources": [
            "KUKA KR-360 Bakım Kılavuzu · Bölüm 7.3 — Servo Aktarma Organları, s. 142–149",
        ],
        "part": "SRV-KR360-A3",
    },
    "M-1190": {
        "answer": (
            "M-1190 (Ana Mil Rulman Titreşim Eşiği Aşıldı): Kök neden, ana mil ön "
            "rulmanında yorulma başlangıcıdır; titreşim spektrumunda dış bilezik geçiş "
            "frekansı (BPFO) baskındır. Hasar erken evrede, planlı değişim önerilir. "
            "İlgili parça RLM-6310-ZZ."
        ),
        "sources": [
            "Schuler HP-2 Bakım Kılavuzu · Bölüm 5.1 — Ana Mil Yatakları, s. 61–66",
        ],
        "part": "RLM-6310-ZZ",
    },
    "P-0834": {
        "answer": (
            "P-0834 (Püskürtme Nozülü Tıkanıklığı): Kök neden, nozülde kurumuş boya "
            "birikintisidir; boya viskozitesi tedarikçi parti değişiminde sapabilir. "
            "İlgili parça NZL-5500-12."
        ),
        "sources": [
            "ABB IRB-5500 Boya Robotu Kılavuzu · Bölüm 9.4 — Nozül Bakımı, s. 203–207",
        ],
        "part": "NZL-5500-12",
    },
    "K-3321": {
        "answer": (
            "K-3321 (Tahrik Kayışı Kayması): Kök neden, tahrik kayışında gerginlik "
            "kaybıdır; gergi mekanizması yeniden ayarlanır. İlgili parça KYS-890-T."
        ),
        "sources": [
            "Bosch Rexroth TS-2plus Kılavuzu · Bölüm 3.6 — Tahrik ve Gergi Sistemi, s. 44–47",
        ],
        "part": "KYS-890-T",
    },
    "HID-220": {
        "answer": (
            "HID-220 (Hidrolik Sıcaklık Yüksek): Yağ sıcaklığı 60°C üzerine çıkar. "
            "Soğutucu fan ve yağ seviyesini kontrol edin; iç kaçak varsa pompayı "
            "E-2208 prosedürüne göre değerlendirin."
        ),
        "sources": ["DMG MORI NLX-2500 Servis Kılavuzu · Bölüm 4.2, s. 87–93"],
        "part": "HYD-4520-B",
    },
    "TTL-101": {
        "answer": (
            "TTL-101 (Genel Tezgah İletişim/Tetikleme Hatası): Saha veri yolu (fieldbus) "
            "zaman aşımı veya tetikleme sinyali kaybı. Önce kablo/konnektör ve PLC G/Ç "
            "durumunu kontrol edin; mekanik parça gerektirmez."
        ),
        "sources": ["Tesis PLC Entegrasyon Notları · Bölüm 2"],
        "part": None,
    },
}


def query_knowledge_base(query: str) -> dict[str, Any]:
    """Kılavuz/RAG sorgusu. Stub ya da gerçek KB, aynı imza.

    Returns:
        {answer, sources[], used_real_kb}
    """
    if config.USE_REAL_KB:
        try:
            return _query_real(query)
        except Exception as exc:  # pragma: no cover - kota/erişim hatası
            stub = _query_stub(query)
            stub["answer"] = (
                "[Gerçek KB erişilemedi, stub cevabı]\n" + stub["answer"]
            )
            stub["error"] = str(exc)
            return stub
    return _query_stub(query)


def _query_stub(query: str) -> dict[str, Any]:
    """Sorgudaki arıza kodunu yakalayıp temsili kılavuz cevabını döndürür."""
    codes = re.findall(r"[A-ZÇĞİÖŞÜ]{1,5}-\d{2,4}", query.upper())
    for code in codes:
        if code in _STUB_KB:
            entry = _STUB_KB[code]
            return {
                "answer": entry["answer"],
                "sources": entry["sources"],
                "used_real_kb": False,
            }
    # Kod yoksa anahtar kelime ile basit eşleştirme.
    q = query.lower()
    for code, entry in _STUB_KB.items():
        if any(w in q for w in ("hidrolik", "pompa", "basınç")) and code == "E-2208":
            return {"answer": entry["answer"], "sources": entry["sources"], "used_real_kb": False}
    return {
        "answer": (
            "Bu sorgu için kılavuzda doğrudan eşleşme bulunamadı. Lütfen arıza kodunu "
            "(örn. E-2208, F-7412) veya parça/sistem adını belirtin."
        ),
        "sources": [],
        "used_real_kb": False,
    }


def _query_real(query: str) -> dict[str, Any]:
    """Gerçek Bedrock Knowledge Base retrieve çağrısı (sync sonrası)."""
    import boto3

    client = boto3.client("bedrock-agent-runtime", region_name=config.AWS_REGION)
    resp = client.retrieve(
        knowledgeBaseId=config.KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": 4}
        },
    )
    results = resp.get("retrievalResults", [])
    passages = [r["content"]["text"] for r in results if r.get("content")]
    sources = []
    for r in results:
        loc = r.get("location", {})
        s3 = loc.get("s3Location", {})
        if s3.get("uri"):
            sources.append(s3["uri"])
    return {
        "answer": "\n\n".join(passages) if passages else "Kılavuzda sonuç bulunamadı.",
        "sources": sources,
        "used_real_kb": True,
    }
