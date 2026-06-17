"""Smoke testleri — yapılandırma ve statik kontroller.

Dosya varlığı, yapısı ve statik kod analizi kontrollerini yapar.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestMcpJson:
    """mcp.json yapılandırma dosyası kontrolleri."""

    def test_file_exists(self):
        mcp_json_path = PROJECT_ROOT / ".kiro" / "settings" / "mcp.json"
        assert mcp_json_path.exists(), f"{mcp_json_path} bulunamadı"

    def test_valid_json(self):
        mcp_json_path = PROJECT_ROOT / ".kiro" / "settings" / "mcp.json"
        content = mcp_json_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "mcpServers" in data

    def test_zerohalt_server_config(self):
        mcp_json_path = PROJECT_ROOT / ".kiro" / "settings" / "mcp.json"
        data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
        server = data["mcpServers"].get("zerohalt-maintenance")
        assert server is not None, "zerohalt-maintenance sunucusu tanımlı değil"
        assert server["command"] == "python"
        assert "mcp_server.py" in server["args"]
        assert "--transport" in server["args"]
        assert "stdio" in server["args"]


class TestRequirementsTxt:
    """requirements.txt içerik kontrolleri."""

    def test_mcp_package_present(self):
        req_path = PROJECT_ROOT / "requirements.txt"
        content = req_path.read_text(encoding="utf-8")
        assert "mcp" in content.lower(), "mcp paketi requirements.txt'de bulunamadı"


class TestMcpServerStaticChecks:
    """mcp_server.py statik kontrolleri."""

    def test_no_direct_sql_import(self):
        """mcp_server.py doğrudan SQL/CSV import'u içermemeli."""
        server_path = PROJECT_ROOT / "mcp_server.py"
        content = server_path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        forbidden_modules = {"sqlite3", "csv", "pandas"}
        imported = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])

        violations = imported & forbidden_modules
        assert not violations, (
            f"mcp_server.py doğrudan {violations} import ediyor; "
            "tüm veri erişimi datasource.py üzerinden olmalı"
        )

    def test_file_syntax_valid(self):
        """mcp_server.py geçerli Python sözdizimi."""
        server_path = PROJECT_ROOT / "mcp_server.py"
        content = server_path.read_text(encoding="utf-8")
        ast.parse(content)  # SyntaxError fırlatırsa test başarısız
