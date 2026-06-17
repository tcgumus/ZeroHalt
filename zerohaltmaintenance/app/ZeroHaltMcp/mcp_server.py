"""ZeroHalt Bakım MCP Sunucusu.

Mevcut veri katmanını (datasource.py) ve bilgi tabanını (src/tools/knowledge.py)
MCP araçları olarak dış istemcilere sunar. Tek dosyalık sunucu, FastMCP SDK kullanır.

Taşıma:
  - Varsayılan: streamable-http (AgentCore uyumlu)
  - --transport stdio: Kiro lokal geliştirme
"""
from __future__ import annotations

import sys
import threading

from mcp.server.fastmcp import FastMCP

import config
import datasource

from typing import Any

# Okuma araçları için zaman aşımı (saniye)
_READ_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Doğrulama ve hata yardımcıları
# ---------------------------------------------------------------------------
VALID_STATUS = {"yeni", "isleniyor", "cozuldu"}


def err(tool: str, message: str, **extra: Any) -> dict[str, Any]:
    """Standart yapısal hata yanıtı (Türkçe)."""
    return {"error": True, "tool": tool, "message": message, **extra}


def require_nonempty(tool: str, name: str, value: Any) -> dict[str, Any] | None:
    """Boş/yalnızca boşluk metni reddeder; veri katmanı sorgulanmaz."""
    if value is None or not str(value).strip():
        return err(tool, f"Geçersiz '{name}': boş olamaz.", field=name)
    return None


def require_positive_int(tool: str, name: str, value: Any) -> dict[str, Any] | None:
    """Pozitif tam sayı değilse reddeder (bool dahil reddedilir)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return err(tool, f"Geçersiz '{name}': pozitif tam sayı olmalı.", field=name)
    return None


def require_status(tool: str, status: str | None) -> dict[str, Any] | None:
    """status None ise serbest; doluysa yalnızca izinli değerler."""
    if status is not None and status not in VALID_STATUS:
        return err(
            tool,
            f"Geçersiz 'status': {sorted(VALID_STATUS)} olmalı.",
            field="status",
            value=status,
        )
    return None


def _safe_call(tool: str, fn, *args, **kwargs) -> Any:
    """İstisna sarmalama: veri katmanı çağrısını try/except ile sarar.

    Başarılıysa fonksiyon sonucunu döndürür.
    İstisna fırlatılırsa yapısal hata döndürür.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return err(tool, f"Veri katmanı hatası: {exc}")


def _safe_call_with_timeout(tool: str, fn, *args, **kwargs) -> Any:
    """Okuma araçları için zaman aşımlı sarmalama (worker thread + join).

    _READ_TIMEOUT saniye içinde tamamlanmazsa yapısal hata döndürür.
    """
    result_holder: list[Any] = []
    error_holder: list[Exception] = []

    def _worker():
        try:
            result_holder.append(fn(*args, **kwargs))
        except Exception as exc:
            error_holder.append(exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_READ_TIMEOUT)

    if t.is_alive():
        return err(tool, f"Zaman aşımı: işlem {_READ_TIMEOUT} saniye içinde tamamlanamadı.")
    if error_holder:
        return err(tool, f"Veri katmanı hatası: {error_holder[0]}")
    return result_holder[0] if result_holder else None


# ---------------------------------------------------------------------------
# FastMCP sunucu örneği
# ---------------------------------------------------------------------------
mcp = FastMCP("zerohalt-maintenance", host="0.0.0.0", stateless_http=True)


# ---------------------------------------------------------------------------
# Parça ve stok araçları (Gereksinim 10, 11)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_part(part_code: str) -> dict[str, Any]:
    """Parça koduna göre parça bilgisi döndürür."""
    check = require_nonempty("get_part", "part_code", part_code)
    if check:
        return check
    result = _safe_call_with_timeout("get_part", datasource.get_part, part_code)
    if isinstance(result, dict) and result.get("error"):
        return result
    if result is None:
        return err("get_part", f"Parça bulunamadı: {part_code}", part_code=part_code)
    return result


@mcp.tool()
def list_all_parts() -> list[dict[str, Any]]:
    """Tüm parçaları listeler."""
    result = _safe_call_with_timeout("list_all_parts", datasource.list_all_parts)
    return result


@mcp.tool()
def list_low_stock() -> list[dict[str, Any]]:
    """Düşük stoklu parçaları listeler (on_hand < safety_stock)."""
    result = _safe_call_with_timeout("list_low_stock", datasource.list_low_stock)
    return result


@mcp.tool()
def get_part_usage_rate(part_code: str) -> dict[str, Any]:
    """Parça tüketim hızını hesaplar."""
    check = require_nonempty("get_part_usage_rate", "part_code", part_code)
    if check:
        return check
    result = _safe_call_with_timeout("get_part_usage_rate", datasource.get_part_usage_rate, part_code)
    return result


@mcp.tool()
def get_substitutes(part_code: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Parça için muadil listesini döndürür."""
    check = require_nonempty("get_substitutes", "part_code", part_code)
    if check:
        return check
    result = _safe_call_with_timeout("get_substitutes", datasource.get_substitutes, part_code)
    return result


# ---------------------------------------------------------------------------
# Olay araçları (Gereksinim 12)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_incidents(status: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """Olayları listeler. Opsiyonel durum filtresi: yeni, isleniyor, cozuldu."""
    check = require_status("list_incidents", status)
    if check:
        return check
    result = _safe_call_with_timeout("list_incidents", datasource.list_incidents, status)
    return result


@mcp.tool()
def get_incident(incident_id: str) -> dict[str, Any]:
    """Olay detayını döndürür."""
    check = require_nonempty("get_incident", "incident_id", incident_id)
    if check:
        return check
    result = _safe_call_with_timeout("get_incident", datasource.get_incident, incident_id)
    if isinstance(result, dict) and result.get("error"):
        return result
    if result is None:
        return err("get_incident", f"Olay bulunamadı: {incident_id}", incident_id=incident_id)
    return result


@mcp.tool()
def get_incident_by_fault(fault_code: str, machine_id: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """Arıza koduna (ve opsiyonel makine) göre olayları döndürür."""
    check = require_nonempty("get_incident_by_fault", "fault_code", fault_code)
    if check:
        return check
    result = _safe_call_with_timeout("get_incident_by_fault", datasource.get_incident_by_fault, fault_code, machine_id)
    if isinstance(result, dict) and result.get("error"):
        return result
    if result is None:
        return []
    return result


# ---------------------------------------------------------------------------
# Bakım geçmişi araçları (Gereksinim 13)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_maintenance_history(fault_code: str | None = None, machine_id: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """Bakım geçmişini filtrelerle sorgular (VE mantığı)."""
    result = _safe_call_with_timeout("get_maintenance_history", datasource.get_maintenance_history, fault_code, machine_id)
    return result


@mcp.tool()
def get_all_maintenance_history() -> list[dict[str, Any]] | dict[str, Any]:
    """Tüm bakım geçmişini döndürür."""
    result = _safe_call_with_timeout("get_all_maintenance_history", datasource.get_all_maintenance_history)
    return result


# ---------------------------------------------------------------------------
# Analiz, raporlama araçları (Gereksinim 14)
# ---------------------------------------------------------------------------


@mcp.tool()
def get_fault_frequency() -> list[dict[str, Any]] | dict[str, Any]:
    """Arıza frekansı raporu döndürür (tekrar sayısına göre azalan)."""
    result = _safe_call_with_timeout("get_fault_frequency", datasource.get_fault_frequency)
    return result


@mcp.tool()
def compute_kpis() -> dict[str, Any]:
    """KPI göstergelerini hesaplar ve döndürür."""
    result = _safe_call_with_timeout("compute_kpis", datasource.compute_kpis)
    return result


@mcp.tool()
def weekly_downtime() -> list | dict[str, Any]:
    """Haftalık duruş raporu (Pzt-Paz, 7 öğe)."""
    result = _safe_call_with_timeout("weekly_downtime", datasource.weekly_downtime)
    return result


# ---------------------------------------------------------------------------
# Bilgi tabanı aracı (Gereksinim 17)
# ---------------------------------------------------------------------------


@mcp.tool()
def query_knowledge_base(query: str) -> dict[str, Any]:
    """Arıza kodu veya sorgu metniyle kılavuz bilgisi arar."""
    check = require_nonempty("query_knowledge_base", "query", query)
    if check:
        return check
    try:
        from src.tools.knowledge import query_knowledge_base as _kb_query
        result = _kb_query(query)
        return result
    except Exception as exc:
        return err("query_knowledge_base", f"Bilgi tabanı hatası: {exc}")


# ---------------------------------------------------------------------------
# Sipariş araçları (Gereksinim 15)
# ---------------------------------------------------------------------------


@mcp.tool()
def create_order_draft(part_code: str, quantity: int, est_cost: float) -> dict[str, Any]:
    """Parça için sipariş taslağı oluşturur."""
    from src.policy import requires_manager_approval as _approval_check

    # Doğrulama
    check = require_nonempty("create_order_draft", "part_code", part_code)
    if check:
        return check
    check = require_positive_int("create_order_draft", "quantity", quantity)
    if check:
        return check
    if not isinstance(est_cost, (int, float)) or isinstance(est_cost, bool) or est_cost < 0:
        return err("create_order_draft", "Geçersiz 'est_cost': 0 veya üzeri sayısal değer olmalı.", field="est_cost")

    # Parça varlığı kontrolü
    part = _safe_call("create_order_draft", datasource.get_part, part_code)
    if isinstance(part, dict) and part.get("error"):
        return part
    if part is None:
        return err("create_order_draft", f"Parça bulunamadı: {part_code}", part_code=part_code)

    # Onay bayrağı
    approval_needed = _approval_check(est_cost)

    # Taslak oluştur
    result = _safe_call(
        "create_order_draft",
        datasource.save_order_draft,
        part_code, quantity, est_cost, approval_needed,
    )
    return result


@mcp.tool()
def list_orders() -> list[dict[str, Any]] | dict[str, Any]:
    """Tüm sipariş taslaklarını listeler (created_at azalan)."""
    result = _safe_call("list_orders", datasource.list_orders)
    return result


# ---------------------------------------------------------------------------
# İş emri araçları (Gereksinim 16)
# ---------------------------------------------------------------------------


@mcp.tool()
def create_work_order(
    fault_id: str,
    root_cause: str,
    steps: str | list[str],
    part_code: str,
    technician: str,
) -> dict[str, Any]:
    """Arıza için iş emri oluşturur."""
    # Zorunlu alan kontrolü
    for field_name, field_value in [
        ("fault_id", fault_id),
        ("root_cause", root_cause),
        ("part_code", part_code),
        ("technician", technician),
    ]:
        check = require_nonempty("create_work_order", field_name, field_value)
        if check:
            return check

    # steps normalizasyonu
    if isinstance(steps, str):
        steps_list = [line.strip() for line in steps.split("\n") if line.strip()]
    else:
        steps_list = [s.strip() for s in steps if s and str(s).strip()]

    if not steps_list:
        return err("create_work_order", "Geçersiz 'steps': boş olamaz.", field="steps")

    result = _safe_call(
        "create_work_order",
        datasource.save_work_order,
        fault_id, root_cause, steps_list, part_code, technician,
    )
    return result


@mcp.tool()
def list_work_orders() -> list[dict[str, Any]] | dict[str, Any]:
    """Tüm iş emirlerini listeler (created_at azalan)."""
    result = _safe_call("list_work_orders", datasource.list_work_orders)
    return result


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
def _bootstrap() -> None:
    """Başlatma: DB tohumlamasını tetikle, OFFLINE_MODE kontrolü yap."""
    # Veri katmanını hazırla (ilk _connect çağrısı seed'i garanti eder)
    datasource._connect().close()

    if config.OFFLINE_MODE:
        return  # Bedrock'a hiç dokunma

    # OFFLINE_MODE=false ise Bedrock bağlantı denemesi
    try:
        _probe_bedrock()
    except Exception as exc:
        print(f"[uyarı] Bedrock bağlantısı kurulamadı: {exc}", file=sys.stderr)


def _probe_bedrock() -> None:
    """Hafif Bedrock bağlantı denemesi (placeholder)."""
    # Gerçek uygulama: boto3 bedrock-runtime client ile basit bir list çağrısı.
    # Şimdilik OFFLINE_MODE=true olduğu için buraya düşmeyecek.
    pass


# ---------------------------------------------------------------------------
# Taşıma seçimi ve çalıştırma
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # --transport stdio argümanını kontrol et
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1] == "stdio":
            transport = "stdio"
        else:
            transport = "sse"
    else:
        transport = "sse"

    _bootstrap()
    mcp.run(transport=transport)
