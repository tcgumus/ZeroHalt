"""CLI demo akışı — kabul kriteri senaryosunu uçtan uca çalıştırır.

Kullanım:
    python app.py                 # varsayılan arıza (E-2208) senaryosu
    python app.py F-7412          # belirli arıza kodu
    python app.py --list          # aktif arıza kuyruğu
    python app.py --web           # web panelini başlat (Flask)
"""
from __future__ import annotations

import sys

# Windows konsolunda Türkçe karakterler için UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import config
import datasource
from src import agent, policy


def _print_header() -> None:
    print("=" * 72)
    print("  OTONOM BAKIM VE PARÇA YÖNETİM SİSTEMİ — Demo")
    print(f"  Mod: {'OFFLINE (Bedrock yok)' if config.OFFLINE_MODE else 'ONLINE (Bedrock)'}"
          f" | Model: {config.BEDROCK_MODEL_ID} | KB gerçek: {config.USE_REAL_KB}")
    print("=" * 72)


def list_incidents() -> None:
    _print_header()
    print("\nAktif arıza kuyruğu:\n")
    for inc in datasource.list_incidents():
        print(f"  {inc['incident_id']:>10}  {inc['fault_code']:<8}  "
              f"{inc['status']:<10}  {inc['machine_id']:<22}  {inc['title']}")


def run_scenario(fault_code: str) -> None:
    _print_header()
    incident = datasource.get_incident_by_fault(fault_code)
    machine = incident["machine_id"] if incident else "Bilinmeyen Makine"
    title = incident["title"] if incident else ""
    print(f"\n▶ Arıza işleniyor: {fault_code} — {machine}\n")

    result = agent.run_diagnosis(fault_code, machine, title)

    print("Ajan araç çağrı zinciri (tool-use):")
    for i, step in enumerate(result["trace"], 1):
        ok = "error" not in (step["output"] if isinstance(step["output"], dict) else {})
        print(f"  {i}. {step['tool']}({step['input']})  {'✓' if ok else '✗'}")

    print("\n" + "-" * 72)
    print(result["summary"])
    print("-" * 72)

    # İnsan onayı adımı görünür olmalı (CLI'da ayrı adım).
    draft = result.get("order_draft")
    if draft:
        print("\n[İNSAN ONAYI ADIMI]")
        print(policy.approval_banner(draft))
        print("Bu demo'da otomatik onaylanmaz. Onaylamak için:")
        print(f"  python -c \"from src import policy; "
              f"print(policy.decide('{draft['draft_id']}', True, 'Elif Demirtaş'))\"")


def main() -> None:
    args = sys.argv[1:]
    if "--web" in args:
        from web.server import main as web_main
        web_main()
        return
    if "--list" in args:
        list_incidents()
        return
    fault_code = next((a for a in args if not a.startswith("-")), "E-2208")
    run_scenario(fault_code)


if __name__ == "__main__":
    main()
