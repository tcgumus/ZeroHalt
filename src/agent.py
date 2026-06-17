"""Otonom Bakım ajanı — tool-use orkestrasyon döngüsü.

İki çalışma modu, AYNI yapısal sonucu üretir:
  - OFFLINE_MODE=true  -> deterministik akış (Bedrock'suz; demo/CI).
  - OFFLINE_MODE=false -> boto3 Bedrock `converse` tool-use döngüsü.

Sonuç (run_diagnosis) panel/CLI/web tarafından tüketilir:
  {fault_code, machine_id, root_cause, confidence, sources, evidence,
   part, stock, substitutes, order_draft, work_order, summary, trace, mode}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import config
import datasource
from src import policy
from src import prompts
from src import tools as toolkit

_FAULT_SIG: Optional[dict[str, Any]] = None


def _fault_signatures() -> dict[str, Any]:
    global _FAULT_SIG
    if _FAULT_SIG is None:
        path = config.DATA_DIR / "fault_signatures.json"
        _FAULT_SIG = json.loads(Path(path).read_text(encoding="utf-8"))
    return _FAULT_SIG


# ---------------------------------------------------------------------------
# Yapısal teşhis — her iki mod ortak araç katmanını kullanır
# ---------------------------------------------------------------------------
def run_diagnosis(
    fault_code: str,
    machine_id: str,
    title: str = "",
    technician: Optional[str] = None,
    image_b64: Optional[str] = None,
) -> dict[str, Any]:
    """Bir arıza için uçtan uca teşhis zincirini çalıştırır.

    CHAT_ONLINE=True ise Bedrock tool-use ile MCP dinamik akış;
    aksi halde offline deterministik akış.
    """
    if config.CHAT_ONLINE or not config.OFFLINE_MODE:
        try:
            return _run_online(fault_code, machine_id, title, technician, image_b64)
        except Exception:
            pass  # Bedrock erişilemezse offline'a düş
    return _run_offline(fault_code, machine_id, title, technician, image_b64)


# ---------------------------------------------------------------------------
# OFFLINE — deterministik oyun kitabı
# ---------------------------------------------------------------------------
def _run_offline(
    fault_code: str,
    machine_id: str,
    title: str,
    technician: Optional[str],
    image_b64: Optional[str],
) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []

    def call(name: str, **kwargs):
        out = toolkit.dispatch(name, kwargs)
        trace.append({"tool": name, "input": kwargs, "output": out})
        return out

    sig = _fault_signatures().get(fault_code, {})

    # 1) Kök neden — KB + geçmiş kayıtlar
    kb = call("query_knowledge_base", query=f"{fault_code} kök neden onarım")
    history = datasource.get_maintenance_history(fault_code=fault_code)

    # 2) Parça belirle (gerekirse görüntüden)
    part_code = sig.get("part_code")
    if not part_code and image_b64:
        ident = call("identify_part", image_b64=image_b64)
        part_code = ident.get("part_code")
    if not part_code:
        part_code = "HYD-4520-B"  # demo varsayılanı

    info = call("part_info", part_code=part_code)
    stock = call("stock_lookup", part_code=part_code)

    # 3) Stok emniyet stoğunun altındaysa muadil
    substitutes: list[dict[str, Any]] = []
    if stock.get("below_safety"):
        substitutes = call("find_substitutes", part_code=part_code)

    # 4) Sipariş taslağı (gerekiyorsa) — ASLA onaylanmaz.
    #    Miktar artık sabit değil; create_order_draft tedarik süresi + açık talep +
    #    emniyet stoğundan şeffaf formülle hesaplar (quantity geçilmez).
    order_draft = None
    if stock.get("below_safety"):
        order_draft = call("create_order_draft", part_code=part_code)

    # 5) İş emri
    tech = technician or sig.get("technician", "Atanacak Teknisyen")
    steps = sig.get("steps", ["Arızayı kılavuza göre değerlendir ve onar."])
    incident = datasource.get_incident_by_fault(fault_code, machine_id)
    fault_id = incident["incident_id"] if incident else fault_code
    work_order = call(
        "create_work_order",
        fault_id=fault_id,
        root_cause=kb.get("answer", ""),
        steps=steps,
        part_code=part_code,
        technician=tech,
    )

    confidence = sig.get("confidence", 80)
    evidence = sig.get("evidence", [])
    summary = _build_summary(
        fault_code, machine_id, kb, confidence, info, stock,
        substitutes, order_draft, work_order,
    )

    return {
        "mode": "offline",
        "fault_code": fault_code,
        "machine_id": machine_id,
        "title": title,
        "root_cause": kb.get("answer", ""),
        "confidence": confidence,
        "sources": kb.get("sources", []),
        "evidence": evidence,
        "history": history,
        "part": info,
        "stock": stock,
        "substitutes": substitutes,
        "order_draft": order_draft,
        "work_order": work_order,
        "summary": summary,
        "trace": trace,
    }


def _build_summary(
    fault_code, machine_id, kb, confidence, info, stock,
    substitutes, order_draft, work_order,
) -> str:
    lines = [
        f"🔧 {machine_id} — Arıza {fault_code} teşhis özeti",
        "",
        f"1) KÖK NEDEN (güven %{confidence}): {kb.get('answer', '')}",
    ]
    if kb.get("sources"):
        lines.append(f"   Kaynak: {kb['sources'][0]}")
    lines.append("")
    lines.append(
        f"2) PARÇA / STOK: {info.get('name')} ({stock.get('part_code')}) — "
        f"eldeki {stock.get('on_hand')}, emniyet stoğu {stock.get('safety_stock')}."
    )
    if stock.get("below_safety"):
        lines[-1] += " ⚠️ Stok emniyet seviyesinin ALTINDA."
    if substitutes:
        approved = [s for s in substitutes if s["approved"]]
        if approved:
            s = approved[0]
            lines.append(
                f"   Önerilen muadil: {s['substitute_code']} ({s['name']}) — "
                f"stokta {s['on_hand']} adet, onaylı."
            )
    lines.append("")
    if order_draft:
        lines.append("3) SİPARİŞ TASLAĞI: " + policy.approval_banner(order_draft))
        if order_draft.get("rationale"):
            lines.append("   Miktar gerekçesi: " + order_draft["rationale"])
        lines.append("   ⛔ Bu taslak ajan tarafından ONAYLANMAZ — insan onayı bekliyor.")
    else:
        lines.append("3) SİPARİŞ: Mevcut stok yeterli, sipariş taslağı gerekmedi.")
    lines.append("")
    lines.append(
        f"4) İŞ EMRİ: {work_order.get('work_order_id')} oluşturuldu — "
        f"teknisyen {work_order.get('technician')}, {len(work_order.get('steps', []))} adım."
    )
    lines.append("")
    lines.append("➡️ Sıradaki adım: Sipariş taslağı için bakım planlama sorumlusunun onayı.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ONLINE — Bedrock converse tool-use döngüsü
# ---------------------------------------------------------------------------
def _run_online(
    fault_code: str,
    machine_id: str,
    title: str,
    technician: Optional[str],
    image_b64: Optional[str],
) -> dict[str, Any]:
    from src.bedrock_client import BedrockClient

    client = BedrockClient()
    user_text = prompts.initial_user_message(fault_code, machine_id, title)
    if technician:
        user_text += f"\nAtanacak teknisyen: {technician}."

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": user_text}]}
    ]
    system = [{"text": prompts.SYSTEM_PROMPT}]
    tool_config = {"tools": toolkit.TOOL_SPECS}

    trace: list[dict[str, Any]] = []
    captured: dict[str, Any] = {}
    final_text = ""

    for _ in range(12):  # döngü güvenlik sınırı
        resp = client.converse(messages, system=system, tool_config=tool_config)
        out_msg = resp.get("output", {}).get("message", {})
        messages.append(out_msg)
        stop = resp.get("stopReason")

        tool_uses = [b for b in out_msg.get("content", []) if "toolUse" in b]
        text_blocks = [b["text"] for b in out_msg.get("content", []) if "text" in b]
        if text_blocks:
            final_text = "\n".join(text_blocks)

        if stop != "tool_use" or not tool_uses:
            break

        tool_results = []
        for tu in tool_uses:
            tu = tu["toolUse"]
            name, tin, tuid = tu["name"], tu.get("input", {}), tu["toolUseId"]
            result = toolkit.dispatch(name, tin)
            trace.append({"tool": name, "input": tin, "output": result})
            captured[name] = result
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tuid,
                        "content": [{"json": _jsonable(result)}],
                    }
                }
            )
        messages.append({"role": "user", "content": tool_results})

    # Sonuçları topla — modelin kendi analizi üzerinden
    kb_result = captured.get("query_knowledge_base", {})
    root_cause = kb_result.get("answer", "") if isinstance(kb_result, dict) else ""

    # Confidence ve evidence: model trace'den çıkar veya geçmiş veriden hesapla
    history = captured.get("get_maintenance_history", [])
    freq = captured.get("get_fault_frequency", [])

    # Dinamik confidence hesapla: geçmiş kayıt varsa yüksek, yoksa orta
    if isinstance(history, list) and len(history) >= 2:
        confidence = 92
    elif isinstance(history, list) and len(history) == 1:
        confidence = 85
    else:
        confidence = 75

    # Evidence: KB kaynaklarından + stok durumundan dinamik oluştur
    evidence = []
    if kb_result.get("sources"):
        evidence.append(f"Kılavuz kaynağı: {kb_result['sources'][0]}")
    stock_data = captured.get("stock_lookup", {})
    if isinstance(stock_data, dict) and stock_data.get("below_safety"):
        evidence.append(f"Stok kritik: {stock_data.get('on_hand')}/{stock_data.get('safety_stock')} (emniyet altında)")
    if isinstance(history, list):
        for h in history[:2]:
            if isinstance(h, dict) and h.get("root_cause"):
                evidence.append(f"Geçmiş kayıt: {h['root_cause'][:80]}")

    # Muadil garantisi: stok kritikse ve model muadil çağırmadıysa biz çağıralım
    substitutes = captured.get("find_substitutes", [])
    if isinstance(stock_data, dict) and stock_data.get("below_safety") and not substitutes:
        part_code = stock_data.get("part_code") or (captured.get("part_info", {}) or {}).get("part_code")
        if part_code:
            substitutes = toolkit.dispatch("find_substitutes", {"part_code": part_code})
            trace.append({"tool": "find_substitutes", "input": {"part_code": part_code}, "output": substitutes})

    return {
        "mode": "online",
        "fault_code": fault_code,
        "machine_id": machine_id,
        "title": title,
        "root_cause": root_cause,
        "confidence": confidence,
        "sources": kb_result.get("sources", []) if isinstance(kb_result, dict) else [],
        "evidence": evidence,
        "part": captured.get("part_info", {}),
        "stock": stock_data,
        "substitutes": substitutes,
        "order_draft": captured.get("create_order_draft"),
        "work_order": captured.get("create_work_order"),
        "summary": final_text,
        "trace": trace,
    }


def _jsonable(obj: Any) -> Any:
    """toolResult JSON bloğu obje (dict) olmalı; liste ise sar."""
    if isinstance(obj, dict):
        return obj
    return {"result": obj}


# ---------------------------------------------------------------------------
# Asistan sohbeti
# ---------------------------------------------------------------------------
def chat(question: str) -> str:
    """Serbest sohbet — canlı veriyle yanıtlar (offline: kural tabanlı)."""
    if config.CHAT_ONLINE or not config.OFFLINE_MODE:
        try:
            return _chat_online(question)
        except Exception as exc:
            # Bağlantı hatasını kullanıcıya göster (debug).
            import traceback
            err_detail = traceback.format_exc()
            return (
                f"⚠️ Bedrock bağlantı hatası: {exc}\n\n"
                f"Detay:\n```\n{err_detail}\n```"
            )
    return _chat_offline(question)


def _chat_offline(question: str) -> str:
    t = question.lower()
    if "hyd" in t or "pompa" in t:
        s = toolkit.dispatch("stock_lookup", {"part_code": "HYD-4520-B"})
        subs = toolkit.dispatch("find_substitutes", {"part_code": "HYD-4520-B"})
        appr = next((x for x in subs if x["approved"]), None)
        msg = (
            f"HYD-4520-B ({s['name']}): stokta {s['on_hand']} adet "
            f"(emniyet stoğu {s['safety_stock']} — "
            f"{'KRİTİK' if s['below_safety'] else 'normal'})."
        )
        if appr:
            msg += f" Onaylı muadil {appr['substitute_code']} stokta {appr['on_hand']} adet."
        return msg
    if "sipariş" in t or "siparis" in t:
        orders = datasource.list_orders()
        if not orders:
            return "Şu an bekleyen sipariş taslağı yok."
        pend = [o for o in orders if o["status"] == "pending_approval"]
        lines = ["Bekleyen sipariş taslakları:"]
        for o in pend[:5]:
            lines.append(
                f"• {o['draft_id']} — {o['part_code']} × {o['quantity']}, "
                f"{o['est_cost']} TL, insan onayı bekliyor."
            )
        return "\n".join(lines) if pend else "Bekleyen onay yok; tüm taslaklar karara bağlandı."
    if "iş emri" in t or "is emri" in t or "wo-" in t:
        wos = datasource.list_work_orders()
        if not wos:
            return "Henüz iş emri oluşturulmadı."
        w = wos[0]
        return (
            f"{w['work_order_id']} ({w['part_code']} değişimi): teknisyen "
            f"{w['technician']}, {len(w['steps'])} adım, durum {w['status']}."
        )
    if "muadil" in t:
        subs = toolkit.dispatch("find_substitutes", {"part_code": "HYD-4520-B"})
        appr = [s for s in subs if s["approved"]]
        if appr:
            s = appr[0]
            return (
                f"HYD-4520-B için onaylı muadil: {s['substitute_code']} ({s['name']}), "
                f"stokta {s['on_hand']} adet."
            )
        return "Onaylı muadil bulunamadı."
    if "stok" in t or "duruş" in t or "durus" in t:
        low = datasource.list_low_stock()
        lines = ["Emniyet stoğunun altındaki parçalar:"]
        for p in low[:5]:
            lines.append(f"• {p['part_code']} ({p['name']}): {p['on_hand']}/{p['safety_stock']}")
        return "\n".join(lines)
    return (
        "Bu soruyu eşleştiremedim. Parça kodu (örn. HYD-4520-B), 'sipariş durumu', "
        "'muadil', 'iş emri' veya 'stok' gibi bir ifadeyle tekrar deneyin."
    )


def _chat_online(question: str) -> str:
    """boto3 Bedrock Runtime converse API ile tool-use sohbet.

    Akış:
    1. Kullanıcı sorusunu + MCP tool tanımlarını Bedrock'a gönder
    2. Model tool çağrısı isterse, ilgili MCP tool'u çağır
    3. Tool sonucunu modele geri gönder
    4. Model son yanıtı üret
    """
    from src.bedrock_client import BedrockClient
    import datasource

    client = BedrockClient()

    # MCP tool tanımları (Bedrock toolConfig formatında)
    tool_config = {
        "tools": [
            {
                "toolSpec": {
                    "name": "list_all_parts",
                    "description": "Tüm parçaları listeler (kod, isim, kategori, stok bilgisi).",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "list_low_stock",
                    "description": "Emniyet stoğunun altındaki parçaları listeler.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "get_part",
                    "description": "Parça koduna göre detaylı bilgi döndürür.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"part_code": {"type": "string", "description": "Parça kodu (örn. HYD-4520-B)"}},
                            "required": ["part_code"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "get_substitutes",
                    "description": "Bir parçanın muadil listesini döndürür.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"part_code": {"type": "string", "description": "Parça kodu"}},
                            "required": ["part_code"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "list_incidents",
                    "description": "Arıza olaylarını listeler. Opsiyonel durum filtresi: yeni, isleniyor, cozuldu.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"status": {"type": "string", "description": "Filtre: yeni, isleniyor, cozuldu"}},
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "get_incident",
                    "description": "Olay ID ile detay döndürür.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"incident_id": {"type": "string"}},
                            "required": ["incident_id"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "compute_kpis",
                    "description": "Bakım KPI göstergelerini hesaplar (MTBF, MTTR, aktif arıza sayısı, çözüm oranı vb.).",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "get_fault_frequency",
                    "description": "Arıza frekansı raporu döndürür (en çok tekrar eden arızalar).",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "weekly_downtime",
                    "description": "Haftalık duruş raporu (Pzt-Paz, saat cinsinden).",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "list_orders",
                    "description": "Sipariş taslaklarını listeler.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "list_work_orders",
                    "description": "İş emirlerini listeler.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "query_knowledge_base",
                    "description": "Arıza kodu veya sorgu metniyle bakım kılavuzunda bilgi arar.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"query": {"type": "string", "description": "Arama sorgusu"}},
                            "required": ["query"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "create_order_draft",
                    "description": "Parça için sipariş taslağı oluşturur. Taslak insan onayı bekler, ajan onaylamaz. part_code zorunlu, quantity ve est_cost opsiyonel.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "part_code": {"type": "string", "description": "Sipariş edilecek parça kodu"},
                                "quantity": {"type": "integer", "description": "Adet (opsiyonel, verilmezse hesaplanır)"},
                                "est_cost": {"type": "number", "description": "Tahmini maliyet TL (opsiyonel)"},
                            },
                            "required": ["part_code"],
                        }
                    },
                }
            },
        ]
    }

    # MCP tool dispatcher
    def _call_mcp_tool(name: str, args: dict) -> Any:
        import json as _json
        tool_map = {
            "list_all_parts": lambda _: datasource.list_all_parts(),
            "list_low_stock": lambda _: datasource.list_low_stock(),
            "get_part": lambda a: datasource.get_part(a.get("part_code", "")),
            "get_substitutes": lambda a: datasource.get_substitutes(a.get("part_code", "")),
            "list_incidents": lambda a: datasource.list_incidents(a.get("status")),
            "get_incident": lambda a: datasource.get_incident(a.get("incident_id", "")),
            "compute_kpis": lambda _: datasource.compute_kpis(),
            "get_fault_frequency": lambda _: datasource.get_fault_frequency(),
            "weekly_downtime": lambda _: datasource.weekly_downtime(),
            "list_orders": lambda _: datasource.list_orders(),
            "list_work_orders": lambda _: datasource.list_work_orders(),
            "query_knowledge_base": lambda a: _kb_query(a.get("query", "")),
            "create_order_draft": lambda a: _create_order(a),
        }
        fn = tool_map.get(name)
        if fn is None:
            return {"error": f"Bilinmeyen tool: {name}"}
        try:
            result = fn(args)
            return result if result is not None else {"error": f"Sonuç bulunamadı"}
        except Exception as exc:
            return {"error": str(exc)}

    def _kb_query(query: str):
        try:
            from src.tools.knowledge import query_knowledge_base
            return query_knowledge_base(query)
        except Exception:
            return {"message": "Bilgi tabanı erişilemedi."}

    def _create_order(args: dict):
        part_code = args.get("part_code", "")
        part = datasource.get_part(part_code)
        if not part:
            return {"error": f"Parça bulunamadı: {part_code}"}
        # Stok kontrolü: emniyet stoğunun üstündeyse sipariş gereksiz
        on_hand = part.get("on_hand", 0)
        safety = part.get("safety_stock", 0)
        if on_hand >= safety:
            return {"rejected": True, "message": f"{part_code} stoğu yeterli ({on_hand}/{safety}), sipariş gerekmiyor."}
        quantity = args.get("quantity") or max(1, safety - on_hand)
        est_cost = args.get("est_cost", part.get("unit_cost", 1000) * quantity)
        from src import policy
        approval_needed = policy.requires_manager_approval(est_cost)
        return datasource.save_order_draft(part_code, quantity, est_cost, approval_needed)

    system = [{"text": (
        "Sen FNSS Gölbaşı Üretim Tesisi'nin bakım asistanısın. "
        "Kullanıcının sorularını yanıtlamak için MCP tool'larını kullan. "
        "Yanıtlarını Türkçe ver, kısa ve net ol. "
        "Tool sonuçlarını kullanarak somut bilgi ver (stok adetleri, arıza kodları vb.). "
        "Kullanıcı sipariş taslağı oluşturmak isterse create_order_draft tool'unu çağır."
    )}]

    messages = [{"role": "user", "content": [{"text": question}]}]
    tool_calls_log = []

    # İlk çağrı
    resp = client.converse(messages, system=system, tool_config=tool_config)
    stop = resp.get("stopReason", "")

    # Tool-use döngüsü (max 3 iterasyon)
    for _ in range(3):
        if stop != "tool_use":
            break

        out_msg = resp.get("output", {}).get("message", {})
        messages.append(out_msg)

        # Tool çağrılarını işle
        tool_results = []
        for block in out_msg.get("content", []):
            if "toolUse" in block:
                tu = block["toolUse"]
                tool_name = tu["name"]
                tool_input = tu.get("input", {})
                tool_id = tu["toolUseId"]

                # MCP tool'u çağır
                import json as _json
                result = _call_mcp_tool(tool_name, tool_input)
                result_str = _json.dumps(result, ensure_ascii=False, default=str)

                tool_calls_log.append({"tool": tool_name, "input": tool_input})

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_id,
                        "content": [{"json": result if isinstance(result, dict) else {"data": result}}],
                    }
                })

        messages.append({"role": "user", "content": tool_results})
        resp = client.converse(messages, system=system, tool_config=tool_config)
        stop = resp.get("stopReason", "")

    # Son yanıtı çıkar
    out_msg = resp.get("output", {}).get("message", {})
    text_blocks = [b["text"] for b in out_msg.get("content", []) if "text" in b]
    answer = "\n".join(text_blocks).strip() or "Yanıt üretilemedi."

    # Tool çağrı logunu ekle (demo görselliği için)
    if tool_calls_log:
        log_lines = "\n".join(
            f"  🔧 {tc['tool']}({', '.join(f'{k}={v}' for k, v in tc['input'].items()) if tc['input'] else ''})"
            for tc in tool_calls_log
        )
        answer = f"📡 MCP Tool Çağrıları:\n{log_lines}\n\n{answer}"

    return answer
