"""Tool kayıt defteri: Bedrock `toolConfig` spec'leri + dispatch.

`TOOL_SPECS` doğrudan `converse(toolConfig={"tools": TOOL_SPECS})` olarak geçirilir.
`dispatch(name, input)` ilgili Python fonksiyonunu çağırıp JSON-serileştirilebilir
sonuç döndürür. Tüm tool'lar Bedrock olmadan da doğrudan çağrılabilir.
"""
from __future__ import annotations

from typing import Any, Callable

from src.tools.insights import (
    detect_recurring_faults,
    predict_part_shortage,
    preventive_insights,
)
from src.tools.knowledge import query_knowledge_base
from src.tools.orders import create_order_draft
from src.tools.parts import identify_part, part_info
from src.tools.stock import stock_lookup
from src.tools.substitutes import find_substitutes
from src.tools.work_orders import create_work_order

# Bedrock converse toolConfig formatı.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "query_knowledge_base",
            "description": (
                "Bakım kılavuzlarında (RAG) arama yapar. Arıza kodunun kök nedenini, "
                "onarım prosedürünü ve ilgili parçayı bulmak için kullan."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Arıza kodu veya doğal dil sorgusu (örn. 'E-2208 kök neden').",
                        }
                    },
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "part_info",
            "description": "Bir parçanın teknik bilgisini (özellik, kullanıldığı varyantlar) döndürür.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "part_code": {"type": "string", "description": "Parça kodu (örn. HYD-4520-B)."}
                    },
                    "required": ["part_code"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "stock_lookup",
            "description": "Parçanın stok durumunu (eldeki, emniyet stoğu, tedarik süresi) döndürür.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "part_code": {"type": "string", "description": "Parça kodu."}
                    },
                    "required": ["part_code"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "identify_part",
            "description": (
                "Parça fotoğrafından parça kodunu tanımlar (multimodal). Görüntü base64 "
                "veya metin ipucu ile çağrılabilir."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "image_b64": {"type": "string", "description": "base64 görüntü (opsiyonel)."},
                        "hint": {"type": "string", "description": "Metin ipucu (opsiyonel)."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "find_substitutes",
            "description": "Stok yetersizse parça için onaylı/şartlı muadilleri döndürür.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "part_code": {"type": "string", "description": "Asıl parça kodu."}
                    },
                    "required": ["part_code"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_order_draft",
            "description": (
                "Sipariş TASLAĞI oluşturur (status=pending_approval). ASLA onaylama; "
                "onay insana bırakılır. quantity verilmezse miktar tedarik süresi + "
                "açık talep + emniyet stoğundan otomatik hesaplanır."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "part_code": {"type": "string"},
                        "quantity": {
                            "type": "integer",
                            "description": "Sipariş adedi (opsiyonel; verilmezse hesaplanır).",
                        },
                    },
                    "required": ["part_code"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_work_order",
            "description": "Teşhis sonrası onarım iş emri oluşturur.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "fault_id": {"type": "string", "description": "Arıza/olay kimliği."},
                        "root_cause": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Onarım adımları.",
                        },
                        "part_code": {"type": "string"},
                        "technician": {"type": "string", "description": "Atanan teknisyen."},
                    },
                    "required": ["fault_id", "root_cause", "steps", "part_code", "technician"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "preventive_insights",
            "description": (
                "Önleyici bakım analizi: geçmiş kayıtlardan tekrar eden arızaları, "
                "çapraz-varyant parça açığı riskini ve proaktif uyarıları döndürür. "
                "Benzer arıza tekrarında veya stok/talep değişiminde kullan."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
]

# tool adı -> çağrılabilir fonksiyon.
_DISPATCH: dict[str, Callable[..., Any]] = {
    "query_knowledge_base": query_knowledge_base,
    "part_info": part_info,
    "stock_lookup": stock_lookup,
    "identify_part": identify_part,
    "find_substitutes": find_substitutes,
    "create_order_draft": create_order_draft,
    "create_work_order": create_work_order,
    "preventive_insights": preventive_insights,
    "detect_recurring_faults": detect_recurring_faults,
    "predict_part_shortage": predict_part_shortage,
}


def dispatch(name: str, tool_input: dict[str, Any]) -> Any:
    """Tool'u adıyla çağırır. Bilinmeyen tool için hata sözlüğü döner."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"Bilinmeyen tool: {name}"}
    try:
        return fn(**(tool_input or {}))
    except TypeError as exc:
        return {"error": f"Geçersiz argüman ({name}): {exc}"}
    except Exception as exc:  # pragma: no cover
        return {"error": f"Tool hatası ({name}): {exc}"}


__all__ = ["TOOL_SPECS", "dispatch"]
