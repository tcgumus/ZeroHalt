"""Çekirdek işlevsellik testleri — mcp_server.py araçları.

datasource ve knowledge mock'lanır; gerçek DB'ye dokunulmaz.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import mcp_server


# ---------------------------------------------------------------------------
# get_part
# ---------------------------------------------------------------------------
class TestGetPart:
    def test_success(self):
        mock_part = {"part_code": "HYD-001", "name": "Pompa", "on_hand": 5}
        with patch.object(mcp_server.datasource, "get_part", return_value=mock_part):
            result = mcp_server.get_part("HYD-001")
        assert result == mock_part

    def test_not_found(self):
        with patch.object(mcp_server.datasource, "get_part", return_value=None):
            result = mcp_server.get_part("HYD-999")
        assert result["error"] is True
        assert "HYD-999" in result["message"]

    def test_empty_param(self):
        result = mcp_server.get_part("   ")
        assert result["error"] is True
        assert result["field"] == "part_code"


# ---------------------------------------------------------------------------
# list_incidents
# ---------------------------------------------------------------------------
class TestListIncidents:
    def test_valid_status(self):
        mock_data = [{"incident_id": "INC-001", "status": "yeni"}]
        with patch.object(mcp_server.datasource, "list_incidents", return_value=mock_data):
            result = mcp_server.list_incidents("yeni")
        assert result == mock_data

    def test_invalid_status(self):
        result = mcp_server.list_incidents("bilinmeyen")
        assert result["error"] is True
        assert "status" in result["message"]

    def test_no_filter(self):
        mock_data = [{"incident_id": "INC-001"}, {"incident_id": "INC-002"}]
        with patch.object(mcp_server.datasource, "list_incidents", return_value=mock_data):
            result = mcp_server.list_incidents(None)
        assert result == mock_data


# ---------------------------------------------------------------------------
# create_order_draft
# ---------------------------------------------------------------------------
class TestCreateOrderDraft:
    def test_success(self):
        mock_part = {"part_code": "HYD-001", "name": "Pompa"}
        mock_draft = {"draft_id": "PO-001", "part_code": "HYD-001", "quantity": 3}
        with patch.object(mcp_server.datasource, "get_part", return_value=mock_part):
            with patch.object(mcp_server.datasource, "save_order_draft", return_value=mock_draft):
                result = mcp_server.create_order_draft("HYD-001", 3, 4000.0)
        assert result == mock_draft

    def test_part_not_found(self):
        with patch.object(mcp_server.datasource, "get_part", return_value=None):
            result = mcp_server.create_order_draft("HYD-999", 2, 1000.0)
        assert result["error"] is True
        assert "bulunamadı" in result["message"]

    def test_invalid_quantity_zero(self):
        result = mcp_server.create_order_draft("HYD-001", 0, 1000.0)
        assert result["error"] is True
        assert result["field"] == "quantity"

    def test_invalid_quantity_bool(self):
        result = mcp_server.create_order_draft("HYD-001", True, 1000.0)
        assert result["error"] is True
        assert result["field"] == "quantity"


# ---------------------------------------------------------------------------
# create_work_order
# ---------------------------------------------------------------------------
class TestCreateWorkOrder:
    def test_success(self):
        mock_wo = {"work_order_id": "WO-001", "status": "olusturuldu"}
        with patch.object(mcp_server.datasource, "save_work_order", return_value=mock_wo):
            result = mcp_server.create_work_order(
                fault_id="INC-001",
                root_cause="Pompa arızası",
                steps="Adım 1\nAdım 2",
                part_code="HYD-001",
                technician="A. Yılmaz",
            )
        assert result == mock_wo

    def test_missing_field(self):
        result = mcp_server.create_work_order(
            fault_id="",
            root_cause="Neden",
            steps="Adım 1",
            part_code="HYD-001",
            technician="Tek",
        )
        assert result["error"] is True
        assert result["field"] == "fault_id"

    def test_empty_steps(self):
        result = mcp_server.create_work_order(
            fault_id="INC-001",
            root_cause="Neden",
            steps="   \n   ",
            part_code="HYD-001",
            technician="Tek",
        )
        assert result["error"] is True
        assert result["field"] == "steps"


# ---------------------------------------------------------------------------
# query_knowledge_base
# ---------------------------------------------------------------------------
class TestQueryKnowledgeBase:
    def test_success(self):
        mock_result = {"answer": "Yanıt", "sources": ["kaynak1"], "used_real_kb": False}
        with patch("mcp_server._kb_query", mock_result, create=True):
            with patch("src.tools.knowledge.query_knowledge_base", return_value=mock_result):
                result = mcp_server.query_knowledge_base("E-2208")
        assert result["answer"] == "Yanıt"
        assert result["used_real_kb"] is False

    def test_empty_query(self):
        result = mcp_server.query_knowledge_base("")
        assert result["error"] is True
        assert result["field"] == "query"

    def test_whitespace_query(self):
        result = mcp_server.query_knowledge_base("   ")
        assert result["error"] is True
