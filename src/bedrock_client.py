"""Bedrock Runtime `converse` + Knowledge Base retrieve sarmalayıcı.

- Kimlik bilgisi koddan değil ortamdan gelir (AWS profili / env / SSO).
- Hesap rate-limit'li olduğundan tüm Bedrock çağrılarına 429 ThrottlingException
  için exponential backoff'lu retry uygulanır.
- Model ID ve API imzaları UYDURULMAZ; boto3 `converse` standart imzası kullanılır.
"""
from __future__ import annotations

import random
import time
from typing import Any, Optional

import config


class ThrottlingError(Exception):
    """Tüm denemeler tükendiğinde fırlatılır."""


def _with_backoff(fn, *args, **kwargs):
    """429/throttling durumunda exponential backoff ile yeniden dener."""
    from botocore.exceptions import ClientError

    delay = config.BEDROCK_BASE_DELAY
    last_exc: Optional[Exception] = None
    for attempt in range(config.BEDROCK_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            throttled = code in {
                "ThrottlingException",
                "TooManyRequestsException",
                "ServiceUnavailableException",
            } or status == 429
            if not throttled:
                raise
            last_exc = exc
            if attempt == config.BEDROCK_MAX_RETRIES - 1:
                break
            sleep_for = min(delay, config.BEDROCK_MAX_DELAY) + random.uniform(0, 0.5)
            time.sleep(sleep_for)
            delay *= 2
    raise ThrottlingError(
        f"Bedrock {config.BEDROCK_MAX_RETRIES} denemede yanıt vermedi (429)."
    ) from last_exc


class BedrockClient:
    """boto3 Bedrock Runtime ince sarmalayıcı."""

    def __init__(self, region: Optional[str] = None, model_id: Optional[str] = None):
        import boto3

        self.region = region or config.AWS_REGION
        self.model_id = model_id or config.BEDROCK_MODEL_ID

        # IAM role / ortam credential'ları otomatik kullanılır.
        self._runtime = boto3.client("bedrock-runtime", region_name=self.region)

    # --- Tool-use converse -------------------------------------------------
    def converse(
        self,
        messages: list[dict[str, Any]],
        system: Optional[list[dict[str, Any]]] = None,
        tool_config: Optional[dict[str, Any]] = None,
        inference_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Tek bir converse çağrısı (backoff'lu). Ham yanıtı döndürür."""
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tool_config:
            kwargs["toolConfig"] = tool_config
        kwargs["inferenceConfig"] = inference_config or {
            "maxTokens": 2048,
            "temperature": 0.2,
        }
        return _with_backoff(self._runtime.converse, **kwargs)

    # --- Multimodal (görüntüden parça tanıma) ------------------------------
    def converse_image(
        self, prompt: str, image_bytes: bytes, image_format: str = "jpeg"
    ) -> str:
        """Görüntüyü image bloğu olarak converse mesajına ekler, metin yanıtı döndürür."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_bytes},
                        }
                    },
                ],
            }
        ]
        resp = self.converse(messages)
        return _extract_text(resp)


def _extract_text(response: dict[str, Any]) -> str:
    """converse yanıtından düz metni çıkarır."""
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(b.get("text", "") for b in blocks if "text" in b).strip()
