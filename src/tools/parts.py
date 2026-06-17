"""part_info + identify_part tool'ları.

identify_part, görüntüyü ayrı bir model değil aynı multimodal Claude/Nova
modeliyle okur. Bedrock erişimi yoksa (offline) hafif bir heuristik döner.
"""
from __future__ import annotations

import base64
import re
from typing import Any, Optional

import config
import datasource

# Nova bazen yanıtı <thinking>...</thinking> ile sarar; JSON ayrıştırmadan önce temizle.
_THINK_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _detect_image_format(data: Optional[bytes]) -> str:
    """Görüntü baytlarından formatı (magic-number) belirler. Bedrock enum: png|jpeg|gif|webp."""
    if not data:
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "jpeg"  # TODO: AWS dokümanından doğrula — desteklenmeyen formatta hata fırlatmak gerekebilir.


def _tokens(text: str) -> set[str]:
    """Basit Türkçe-duyarlı kelime ayıklama (2+ harf)."""
    return {t for t in re.split(r"[^0-9a-zçğıöşü]+", (text or "").lower()) if len(t) > 2}


def _match_candidates(hint: Optional[str], limit: int = 4) -> list[dict[str, Any]]:
    """İpucu metnini parça kod/isim/kategori/specs ile eşleştirip sıralı aday listesi döndürür."""
    if not hint:
        return []
    upper = hint.upper()
    htoks = _tokens(hint)
    scored: list[tuple[int, float, dict[str, Any]]] = []
    for p in datasource.list_all_parts():
        exact = p["part_code"].upper() in upper
        text = f"{p['name']} {p['category']} {p['specs']}"
        overlap = len(htoks & _tokens(text))
        if not exact and overlap == 0:
            continue
        conf = 0.95 if exact else min(0.85, round(0.5 + 0.1 * overlap, 2))
        score = (10 if exact else 0) + overlap
        scored.append((score, conf, p))
    scored.sort(key=lambda x: -x[0])
    return [
        {"part_code": p["part_code"], "name": p["name"], "confidence": conf}
        for _, conf, p in scored[:limit]
    ]


def part_info(part_code: str) -> dict[str, Any]:
    """Parça teknik bilgisi.

    Returns:
        {part_code, name, category, specs, used_in_variants, found}
    """
    part = datasource.get_part(part_code)
    if part is None:
        return {"part_code": part_code, "found": False, "error": "Parça bulunamadı."}
    return {
        "part_code": part["part_code"],
        "name": part["name"],
        "category": part["category"],
        "specs": part["specs"],
        "used_in_variants": part["used_in_variants"],
        "found": True,
    }


def identify_part(
    image_bytes: Optional[bytes] = None,
    image_b64: Optional[str] = None,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    """Parça fotoğrafından parça kodunu tanımlar (multimodal).

    Args:
        image_bytes: Ham görüntü baytları.
        image_b64: base64 kodlanmış görüntü (web katmanından gelir).
        hint: Opsiyonel metin ipucu (örn. kullanıcı notu / OCR etiketi).

    Returns:
        {part_code, name, confidence, source}
    """
    if image_b64 and image_bytes is None:
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            image_bytes = None

    if not config.OFFLINE_MODE and image_bytes:
        try:
            return _identify_via_bedrock(image_bytes, hint)
        except Exception:
            pass  # Bedrock erişilemezse offline heuristik'e düş.

    return _identify_offline(image_bytes, hint)


def _identify_offline(
    image_bytes: Optional[bytes], hint: Optional[str]
) -> dict[str, Any]:
    """Bedrock'suz tanıma — ipucu/dosya adını parça kod/isim ile eşleştirir.

    Eşleşme bulursa en olası parçayı + aday listesini döndürür. Görüntüden
    gerçek tanıma çevrimiçi (Bedrock) mod gerektirir; ipucu yoksa dürüstçe bildirir.
    """
    candidates = _match_candidates(hint)
    if candidates:
        best = candidates[0]
        return {
            "part_code": best["part_code"],
            "name": best["name"],
            "confidence": best["confidence"],
            "candidates": candidates,
            "source": "offline-hint" if best["confidence"] >= 0.9 else "offline-keyword",
        }
    return {
        "part_code": None,
        "name": None,
        "confidence": 0.0,
        "candidates": [],
        "source": "offline-unsupported",
        "message": (
            "Görüntüden otomatik tanıma için çevrimiçi (Bedrock) mod gerekir. "
            "İpucu olarak parça kodu/adı yazın ya da örnek parçalardan seçin."
        ),
    }


def _identify_via_bedrock(image_bytes: bytes, hint: Optional[str]) -> dict[str, Any]:
    """Görüntüyü Bedrock converse'e image bloğu olarak gönderir."""
    import json

    from src.bedrock_client import BedrockClient

    client = BedrockClient()
    known = ", ".join(_known_codes())
    prompt = (
        "Aşağıdaki üretim parçası fotoğrafını incele ve hangi parça koduna ait "
        f"olduğunu söyle. Bilinen parça kodları: {known}. "
        "Yalnızca şu JSON formatında yanıt ver: "
        '{"part_code": "...", "name": "...", "confidence": 0.0-1.0}.'
    )
    if hint:
        prompt += f" Ek ipucu: {hint}"
    image_format = _detect_image_format(image_bytes)
    text = _strip_thinking(client.converse_image(prompt, image_bytes, image_format))
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        data.setdefault("confidence", 0.7)
        data.setdefault("candidates", _match_candidates(hint))
        data["source"] = "bedrock"
        return data
    except Exception:
        return _identify_offline(image_bytes, hint)


def _known_codes() -> list[str]:
    return [p["part_code"] for p in datasource.list_parts()]
