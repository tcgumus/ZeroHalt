"""Property-based tests (Hypothesis) — MCP sunucu doğruluk özellikleri.

Her property, design.md Correctness Properties bölümündeki bir özelliği doğrular.
datasource ve knowledge mock'lanır.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

import mcp_server
import config


# ---------------------------------------------------------------------------
# Yardımcı stratejiler
# ---------------------------------------------------------------------------
json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=50),
)

json_dicts = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
    values=json_primitives,
    min_size=1,
    max_size=10,
)

json_dict_lists = st.lists(json_dicts, min_size=0, max_size=10)

nonempty_text = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
whitespace_text = st.text(alphabet=" \t\n\r", min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# Property 1: Veri katmanı sonucu değiştirilmeden iletilir (passthrough)
# ---------------------------------------------------------------------------
class TestProperty1Passthrough:
    """Araç çıktısı == veri katmanı çıktısı (derin eşitlik)."""

    @given(data=json_dicts)
    @settings(max_examples=50)
    def test_get_part_passthrough(self, data):
        with patch.object(mcp_server.datasource, "get_part", return_value=data):
            result = mcp_server.get_part("VALID-CODE")
        assert result == data

    @given(data=json_dict_lists)
    @settings(max_examples=50)
    def test_list_all_parts_passthrough(self, data):
        with patch.object(mcp_server.datasource, "list_all_parts", return_value=data):
            result = mcp_server.list_all_parts()
        assert result == data

    @given(data=json_dicts)
    @settings(max_examples=50)
    def test_get_part_usage_rate_passthrough(self, data):
        with patch.object(mcp_server.datasource, "get_part_usage_rate", return_value=data):
            result = mcp_server.get_part_usage_rate("VALID-CODE")
        assert result == data


# ---------------------------------------------------------------------------
# Property 2: Sıralama korunur (sıra değişmezi)
# ---------------------------------------------------------------------------
class TestProperty2OrderPreserved:
    """Araç döndürdüğü öğe sırası veri katmanından gelen sırayla birebir aynı."""

    @given(data=json_dict_lists)
    @settings(max_examples=50)
    def test_list_low_stock_order(self, data):
        with patch.object(mcp_server.datasource, "list_low_stock", return_value=data):
            result = mcp_server.list_low_stock()
        assert result == data
        # Sıra tam eşleşmeli
        for i, item in enumerate(result):
            assert item == data[i]

    @given(data=json_dict_lists)
    @settings(max_examples=50)
    def test_get_substitutes_order(self, data):
        with patch.object(mcp_server.datasource, "get_substitutes", return_value=data):
            result = mcp_server.get_substitutes("VALID")
        assert result == data

    @given(data=json_dict_lists)
    @settings(max_examples=50)
    def test_get_fault_frequency_order(self, data):
        with patch.object(mcp_server.datasource, "get_fault_frequency", return_value=data):
            result = mcp_server.get_fault_frequency()
        assert result == data


# ---------------------------------------------------------------------------
# Property 3: Boş / None / bulunamadı sonuçları yer tutucuyla değiştirilmez
# ---------------------------------------------------------------------------
class TestProperty3EmptyPreserved:
    """Boş liste, None veya null alanlı nesne olduğu gibi iletilir."""

    def test_list_low_stock_empty(self):
        with patch.object(mcp_server.datasource, "list_low_stock", return_value=[]):
            assert mcp_server.list_low_stock() == []

    def test_get_substitutes_empty(self):
        with patch.object(mcp_server.datasource, "get_substitutes", return_value=[]):
            assert mcp_server.get_substitutes("X") == []

    def test_list_incidents_empty(self):
        with patch.object(mcp_server.datasource, "list_incidents", return_value=[]):
            assert mcp_server.list_incidents("yeni") == []

    def test_get_incident_by_fault_none(self):
        with patch.object(mcp_server.datasource, "get_incident_by_fault", return_value=None):
            assert mcp_server.get_incident_by_fault("E-2208") == []

    def test_get_maintenance_history_empty(self):
        with patch.object(mcp_server.datasource, "get_maintenance_history", return_value=[]):
            assert mcp_server.get_maintenance_history("E-2208") == []

    def test_dict_with_none_fields(self):
        data = {"part_code": "X", "on_hand": None, "safety_stock": None}
        with patch.object(mcp_server.datasource, "get_part", return_value=data):
            result = mcp_server.get_part("X")
        assert result["on_hand"] is None
        assert result["safety_stock"] is None


# ---------------------------------------------------------------------------
# Property 4: Boş zorunlu metin parametresi reddedilir
# ---------------------------------------------------------------------------
class TestProperty4EmptyTextRejected:
    """Boş/whitespace metin → datasource çağrılmaz, yapısal hata döner."""

    @given(value=whitespace_text)
    @settings(max_examples=30)
    def test_get_part_rejects_empty(self, value):
        mock_fn = MagicMock()
        with patch.object(mcp_server.datasource, "get_part", mock_fn):
            result = mcp_server.get_part(value)
        assert result["error"] is True
        assert result["tool"] == "get_part"
        mock_fn.assert_not_called()

    @given(value=whitespace_text)
    @settings(max_examples=30)
    def test_get_substitutes_rejects_empty(self, value):
        mock_fn = MagicMock()
        with patch.object(mcp_server.datasource, "get_substitutes", mock_fn):
            result = mcp_server.get_substitutes(value)
        assert result["error"] is True
        mock_fn.assert_not_called()

    @given(value=whitespace_text)
    @settings(max_examples=30)
    def test_query_kb_rejects_empty(self, value):
        with patch("src.tools.knowledge.query_knowledge_base") as mock_fn:
            result = mcp_server.query_knowledge_base(value)
        assert result["error"] is True
        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Property 5: Geçersiz değer (tür/aralık/küme dışı) reddedilir
# ---------------------------------------------------------------------------
class TestProperty5InvalidValueRejected:
    """Geçersiz tür/aralık/küme → datasource çağrılmaz."""

    @given(quantity=st.one_of(
        st.integers(max_value=0),
        st.just(True),
        st.just(False),
    ))
    @settings(max_examples=30)
    def test_invalid_quantity_rejected(self, quantity):
        mock_fn = MagicMock()
        with patch.object(mcp_server.datasource, "get_part", return_value={"part_code": "X"}):
            with patch.object(mcp_server.datasource, "save_order_draft", mock_fn):
                result = mcp_server.create_order_draft("HYD-001", quantity, 100.0)
        assert result["error"] is True
        mock_fn.assert_not_called()

    @given(status=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in {"yeni", "isleniyor", "cozuldu"}
    ))
    @settings(max_examples=30)
    def test_invalid_status_rejected(self, status):
        mock_fn = MagicMock()
        with patch.object(mcp_server.datasource, "list_incidents", mock_fn):
            result = mcp_server.list_incidents(status)
        assert result["error"] is True
        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Property 6: Bulunamadı hatası, sorgulanan değeri içerir
# ---------------------------------------------------------------------------
class TestProperty6NotFoundContainsId:
    """Hata mesajı sorgulanan kimliği içerir."""

    @given(code=nonempty_text)
    @settings(max_examples=50)
    def test_get_part_not_found_contains_code(self, code):
        with patch.object(mcp_server.datasource, "get_part", return_value=None):
            result = mcp_server.get_part(code)
        assert result["error"] is True
        assert code in result["message"]

    @given(incident_id=nonempty_text)
    @settings(max_examples=50)
    def test_get_incident_not_found_contains_id(self, incident_id):
        with patch.object(mcp_server.datasource, "get_incident", return_value=None):
            result = mcp_server.get_incident(incident_id)
        assert result["error"] is True
        assert incident_id in result["message"]


# ---------------------------------------------------------------------------
# Property 7: Veri katmanı istisnası yapısal hataya sarmalanır
# ---------------------------------------------------------------------------
class TestProperty7ExceptionWrapped:
    """İstisna → yapısal hata; istisna sızmaz."""

    @given(exc_msg=st.text(min_size=1, max_size=50))
    @settings(max_examples=30)
    def test_get_part_exception_wrapped(self, exc_msg):
        with patch.object(mcp_server.datasource, "get_part", side_effect=RuntimeError(exc_msg)):
            result = mcp_server.get_part("VALID")
        assert result["error"] is True
        assert result["tool"] == "get_part"

    @given(exc_msg=st.text(min_size=1, max_size=50))
    @settings(max_examples=30)
    def test_compute_kpis_exception_wrapped(self, exc_msg):
        with patch.object(mcp_server.datasource, "compute_kpis", side_effect=ValueError(exc_msg)):
            result = mcp_server.compute_kpis()
        assert result["error"] is True
        assert result["tool"] == "compute_kpis"

    @given(exc_msg=st.text(min_size=1, max_size=50))
    @settings(max_examples=30)
    def test_list_all_parts_exception_wrapped(self, exc_msg):
        with patch.object(mcp_server.datasource, "list_all_parts", side_effect=IOError(exc_msg)):
            result = mcp_server.list_all_parts()
        assert result["error"] is True


# ---------------------------------------------------------------------------
# Property 8: Sipariş onay bayrağı eşik kuralına uyar
# ---------------------------------------------------------------------------
class TestProperty8ApprovalThreshold:
    """requires_manager_approval == (est_cost >= ORDER_APPROVAL_THRESHOLD)."""

    @given(est_cost=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_approval_flag_matches_threshold(self, est_cost):
        threshold = config.ORDER_APPROVAL_THRESHOLD
        expected = est_cost >= threshold

        mock_part = {"part_code": "X", "name": "Part"}
        captured = {}

        def fake_save(pc, qty, cost, approval):
            captured["approval"] = approval
            return {"draft_id": "PO-1", "requires_manager_approval": approval}

        with patch.object(mcp_server.datasource, "get_part", return_value=mock_part):
            with patch.object(mcp_server.datasource, "save_order_draft", side_effect=fake_save):
                mcp_server.create_order_draft("X", 1, est_cost)

        assert captured["approval"] == expected


# ---------------------------------------------------------------------------
# Property 9: İş emri adımları normalizasyonu
# ---------------------------------------------------------------------------
class TestProperty9StepsNormalization:
    """Boş satır içermez ve sıra korunur."""

    @given(text=st.text(min_size=1, max_size=200, alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters="\n"
    )))
    @settings(max_examples=50)
    def test_steps_no_empty_lines_order_preserved(self, text):
        # En az bir boş olmayan satır olmalı
        expected_lines = [line.strip() for line in text.split("\n") if line.strip()]
        assume(len(expected_lines) > 0)

        captured = {}

        def fake_save(fid, rc, steps, pc, tech):
            captured["steps"] = steps
            return {"work_order_id": "WO-1", "status": "olusturuldu"}

        with patch.object(mcp_server.datasource, "save_work_order", side_effect=fake_save):
            mcp_server.create_work_order("F1", "Cause", text, "P1", "Tech")

        # Boş satır yok
        for step in captured["steps"]:
            assert step.strip() != ""

        # Sıra korunur
        assert captured["steps"] == expected_lines


# ---------------------------------------------------------------------------
# Property 10: Var olmayan parçaya sipariş oluşturulmaz
# ---------------------------------------------------------------------------
class TestProperty10NoOrderForMissingPart:
    """get_part → None ise save_order_draft çağrılmaz."""

    @given(part_code=nonempty_text)
    @settings(max_examples=50)
    def test_no_draft_for_missing_part(self, part_code):
        mock_save = MagicMock()
        with patch.object(mcp_server.datasource, "get_part", return_value=None):
            with patch.object(mcp_server.datasource, "save_order_draft", mock_save):
                result = mcp_server.create_order_draft(part_code, 1, 100.0)
        assert result["error"] is True
        assert "bulunamadı" in result["message"]
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Property 11: Bilgi tabanı yanıtı sabit yapı sözleşmesini korur
# ---------------------------------------------------------------------------
class TestProperty11KBResponseContract:
    """Sonuç daima answer, sources, used_real_kb alanlarını içerir."""

    @given(query=nonempty_text)
    @settings(max_examples=50)
    def test_kb_response_has_required_fields(self, query):
        mock_result = {
            "answer": "Test yanıtı",
            "sources": ["kaynak"],
            "used_real_kb": False,
        }
        with patch("src.tools.knowledge.query_knowledge_base", return_value=mock_result):
            result = mcp_server.query_knowledge_base(query)
        assert "answer" in result
        assert "sources" in result
        assert "used_real_kb" in result
