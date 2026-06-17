"""Uçtan uca ajan akışı (offline) + policy testleri — kabul kriteri."""
from __future__ import annotations

from src import agent, policy


def test_full_chain_acceptance():
    """Tek arıza kodundan: kök neden -> parça/stok -> muadil -> sipariş taslağı
    (onay bekleyen) -> iş emri zinciri uçtan uca çalışır."""
    r = agent.run_diagnosis("E-2208", "CNC-T04 Torna", "Hidrolik basınç düşüşü")

    assert r["mode"] == "offline"
    # kök neden + güven
    assert r["root_cause"]
    assert r["confidence"] == 92
    # parça/stok
    assert r["part"]["part_code"] == "HYD-4520-B"
    assert r["stock"]["below_safety"] is True
    # muadil (stok düşük olduğu için çağrıldı)
    assert any(s["approved"] for s in r["substitutes"])
    # sipariş taslağı — ASLA onaylı değil
    assert r["order_draft"]["status"] == "pending_approval"
    # iş emri
    assert r["work_order"]["work_order_id"].startswith("WO-")
    # tool-use zinciri sırası
    tools_called = [t["tool"] for t in r["trace"]]
    assert tools_called.index("query_knowledge_base") < tools_called.index("create_work_order")
    assert "create_order_draft" in tools_called


def test_agent_never_auto_approves_order():
    r = agent.run_diagnosis("E-2208", "CNC-T04", "")
    draft = r["order_draft"]
    # Ajan kendi başına onay/red yapamaz.
    assert draft["status"] != "approved"
    assert draft["status"] == "pending_approval"


def test_human_approval_step():
    r = agent.run_diagnosis("K-3321", "MONTAJ-HAT1", "Kayış kayması")
    draft = r["order_draft"]
    decided = policy.decide(draft["draft_id"], approved=True, approver="Elif Demirtaş")
    assert decided["status"] == "approved"
    assert decided["approved_by"] == "Elif Demirtaş"


def test_chat_offline_orders():
    agent.run_diagnosis("E-2208", "CNC-T04", "")  # bir taslak üret
    ans = agent.chat("bekleyen siparişler neler?")
    assert "PO-TASLAK" in ans


def test_policy_threshold():
    assert policy.requires_manager_approval(10000) is True
    assert policy.requires_manager_approval(100) is False
