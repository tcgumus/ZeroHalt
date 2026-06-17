"""Merkezi yapılandırma. Tüm değerler ortamdan (.env) okunur.

Kimlik bilgisi (AWS secret) ASLA burada tutulmaz; boto3 onu AWS profili /
ortam değişkenleri üzerinden alır.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .env varsa yükle (yoksa sessizce geç — ortam değişkenleri yine de okunur).
load_dotenv()

# Proje kök dizini — göreli yolları buna göre çöz.
BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "evet"}


def _path(name: str, default: str) -> Path:
    raw = os.getenv(name, default)
    p = Path(raw)
    return p if p.is_absolute() else BASE_DIR / p


# --- AWS / Bedrock ---------------------------------------------------------
AWS_REGION: str = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_MODEL_ID: str = os.getenv("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")
# AMS_MODEL varsa model ID olarak onu kullan (öncelikli).
_ams_model = os.getenv("AMS_MODEL")
if _ams_model:
    BEDROCK_MODEL_ID = _ams_model
# AWS_KEY ortamda varsa boto3'ün göreceği şekilde dışa aktar.
AWS_KEY: str = os.getenv("AWS_KEY", "")

# --- Knowledge Base (RAG) --------------------------------------------------
KNOWLEDGE_BASE_ID: str = os.getenv("KNOWLEDGE_BASE_ID", "LYKPLY3GMD")
DATA_SOURCE_ID: str = os.getenv("DATA_SOURCE_ID", "E0GIBVCAQM")
USE_REAL_KB: bool = _bool("USE_REAL_KB", False)

# --- Çalışma modu ----------------------------------------------------------
# Offline mod: Bedrock'a hiç bağlanmadan deterministik akış (demo/CI).
OFFLINE_MODE: bool = _bool("OFFLINE_MODE", True)

# Chat-only online: Teşhis offline kalırken asistan sohbeti Bedrock'a gider.
CHAT_ONLINE: bool = _bool("CHAT_ONLINE", False)

# --- Policy / onay ---------------------------------------------------------
ORDER_APPROVAL_THRESHOLD: float = float(os.getenv("ORDER_APPROVAL_THRESHOLD", "5000"))

# --- Veri katmanı ----------------------------------------------------------
DB_PATH: Path = _path("DB_PATH", "data/obpys.db")
DATA_DIR: Path = BASE_DIR / "data"

# --- Bedrock retry/backoff -------------------------------------------------
# Hesap rate-limit'li; 429 ThrottlingException'da exponential backoff.
BEDROCK_MAX_RETRIES: int = int(os.getenv("BEDROCK_MAX_RETRIES", "6"))
BEDROCK_BASE_DELAY: float = float(os.getenv("BEDROCK_BASE_DELAY", "1.0"))
BEDROCK_MAX_DELAY: float = float(os.getenv("BEDROCK_MAX_DELAY", "30.0"))


def summary() -> dict:
    """Hassas olmayan config özeti (loglama/teşhis için)."""
    return {
        "AWS_REGION": AWS_REGION,
        "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
        "KNOWLEDGE_BASE_ID": KNOWLEDGE_BASE_ID,
        "USE_REAL_KB": USE_REAL_KB,
        "OFFLINE_MODE": OFFLINE_MODE,
        "ORDER_APPROVAL_THRESHOLD": ORDER_APPROVAL_THRESHOLD,
        "DB_PATH": str(DB_PATH),
    }
