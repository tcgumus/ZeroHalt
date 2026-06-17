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
    """Bir arıza için uçtan uca teşhis zincirini çalıştırır."""
    if config.OFFLINE_MODE:
        return _run_offline(fault_code, machine_id, title, technician, image_b64)
    return _run_online(fault_code, machine_id, title, technician, image_b64)


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

    return {
        "mode": "online",
        "fault_code": fault_code,
        "machine_id": machine_id,
        "title": title,
        "root_cause": captured.get("query_knowledge_base", {}).get("answer", ""),
        "confidence": _fault_signatures().get(fault_code, {}).get("confidence", 80),
        "sources": captured.get("query_knowledge_base", {}).get("sources", []),
        "evidence": _fault_signatures().get(fault_code, {}).get("evidence", []),
        "part": captured.get("part_info", {}),
        "stock": captured.get("stock_lookup", {}),
        "substitutes": captured.get("find_substitutes", []),
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
    """Bedrock-mantle OpenAI-uyumlu endpoint ile sohbet."""
    import requests

    base_url = f"https://bedrock-mantle.{config.AWS_REGION}.api.aws/v1"
    url = f"{base_url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.AWS_KEY}",
    }

    payload = {
        "model": config.BEDROCK_MODEL_ID,
        "messages": [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "max_tokens": 2048,
        "temperature": 0.2,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        body_text = resp.text[:1500]
        return (
            f"⚠️ Bedrock API hatası ({resp.status_code}):\n{body_text}\n\n"
            f"💡 SCP izni açılmalı: bedrock-mantle:CreateInference"
        )
    data = resp.json()

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return answer.strip() or "Yanıt üretilemedi."
