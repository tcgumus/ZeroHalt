"""Tool katmanı testleri — Bedrock olmadan doğrudan çağrı."""
from __future__ import annotations

from src import tools


def test_stock_lookup_below_safety():
    r = tools.dispatch("stock_lookup", {"part_code": "HYD-4520-B"})
    assert r["found"] is True
    assert r["on_hand"] == 3
    assert r["safety_stock"] == 10
    assert r["below_safety"] is True


def test_stock_lookup_unknown():
    r = tools.dispatch("stock_lookup", {"part_code": "YOK-0000"})
    assert r["found"] is False


def test_part_info():
    r = tools.dispatch("part_info", {"part_code": "HYD-4520-B"})
    assert r["found"] is True
    assert "CNC-T04" in r["used_in_variants"]


def test_find_substitutes_sorted_approved_first():
    subs = tools.dispatch("find_substitutes", {"part_code": "HYD-4520-B"})
    assert len(subs) == 3
    assert subs[0]["approved"] is True
    assert subs[0]["substitute_code"] == "HYD-4520-BR"


def test_create_order_draft_is_pending_and_flags_manager():
    r = tools.dispatch("create_order_draft", {"part_code": "HYD-4520-B", "quantity": 12})
    assert r["status"] == "pending_approval"
    assert r["est_cost"] == 18500.0 * 12
    assert r["requires_manager_approval"] is True


def test_create_order_small_no_manager():
    r = tools.dispatch("create_order_draft", {"part_code": "RLM-6310-ZZ", "quantity": 1})
    assert r["status"] == "pending_approval"
    assert r["requires_manager_approval"] is False  # 420 TL < eşik


def test_create_order_draft_auto_quantity():
    """quantity verilmeyince miktar şeffaf formülle hesaplanır."""
    r = tools.dispatch("create_order_draft", {"part_code": "HYD-4520-B"})
    assert r["status"] == "pending_approval"
    assert r["suggested"] is True
    assert r["rationale"]
    # emniyet stoğu 10, eldeki 3 → en az 7 adet önerilmeli
    assert r["quantity"] >= 7


def test_query_kb_stub_returns_sources():
    r = tools.dispatch("query_knowledge_base", {"query": "E-2208 kök neden"})
    assert r["used_real_kb"] is False
    assert r["sources"]
    assert "HYD-4520-B" in r["answer"]


def test_identify_part_offline_hint():
    r = tools.dispatch("identify_part", {"hint": "etikette HYD-4520-B yazıyor"})
    assert r["part_code"] == "HYD-4520-B"
    assert r["confidence"] >= 0.9


def test_identify_part_keyword_candidates():
    """Serbest metin ipucu sıralı aday listesi döndürür (UC-02 alternatif akış)."""
    r = tools.dispatch("identify_part", {"hint": "hidrolik pompa"})
    codes = [c["part_code"] for c in r["candidates"]]
    assert "HYD-4520-B" in codes
    assert len(r["candidates"]) >= 2


def test_identify_part_no_match_is_honest():
    """Eşleşme yoksa uydurma yapmaz; çevrimiçi mod gerektiğini bildirir."""
    r = tools.dispatch("identify_part", {"hint": "tanimsiz-bir-sey-xyz"})
    assert r["part_code"] is None
    assert r["source"] == "offline-unsupported"
    assert r["candidates"] == []


def test_detect_image_format():
    from src.tools.parts import _detect_image_format
    assert _detect_image_format(b"\x89PNG\r\n\x1a\n....") == "png"
    assert _detect_image_format(b"\xff\xd8\xff\xe0....") == "jpeg"
    assert _detect_image_format(b"GIF89a....") == "gif"
    assert _detect_image_format(b"RIFF\x00\x00\x00\x00WEBP") == "webp"


def test_create_work_order():
    r = tools.dispatch(
        "create_work_order",
        {
            "fault_id": "INC-2208",
            "root_cause": "iç kaçak",
            "steps": ["LOTO", "pompa sök", "yeni pompa tak"],
            "part_code": "HYD-4520-B",
            "technician": "Murat Kaya",
        },
    )
    assert r["work_order_id"].startswith("WO-")
    assert len(r["steps"]) == 3
