"""Streaming LLM functions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.llm_client import (
    LLMConfigError,
    image_to_data_url,
    _ensure_configured,
    _first_configured_api_key,
)


async def call_chat_completion_stream(
    messages: list[dict[str, Any]],
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
):
    """Call OpenAI-compatible endpoint with streaming.
    
    Yields chunks of text as they arrive from the LLM.
    """
    api_key = _first_configured_api_key(api_key, settings.llm_api_key)
    base_url = (base_url or settings.llm_base_url).rstrip("/")
    model = model or settings.llm_model

    if not api_key:
        raise LLMConfigError("LLM_API_KEY is not configured. Please create .env from .env.example.")

    url = f"{base_url}/chat/completions"
    
    print(f"[DEBUG] Streaming call: url={url}, model={model}")
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "stream": True,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            pass
    except Exception as exc:
        print(f"[ERROR] Streaming API call failed: {exc}")
        raise


async def extract_work_ticket_stream(markdown_and_json: str):
    """Stream work ticket extraction."""
    prompt = f"""你是一个工作票信息结构化助手。

下面内容来自 PaddleOCR PPStructureV3 对工作票的识别结果，包括 Markdown 文本、表格和页码信息。

请根据 OCR 内容整理为指定 JSON。

要求：
1. 只输出 JSON，不要输出 Markdown，不要解释。
2. 不要编造信息。
3. 无法确定的字段填 null。

OCR 内容如下：

{markdown_and_json}
""".strip()

    async for chunk in call_chat_completion_stream(
        messages=[
            {"role": "system", "content": "你擅长从中文工作票 OCR 结果中抽取可靠的结构化字段。"},
            {"role": "user", "content": prompt},
        ],
        model=settings.llm_model,
    ):
        yield chunk


async def direct_vision_extract_stream(image_path: Path, prompt: str | None = None):
    """Stream vision model extraction."""
    _ensure_configured(vision=True)

    user_prompt = prompt or "请直接识别这张图片中的内容，并输出你认为合适的结果。"
    data_url = image_to_data_url(image_path)

    vision_api_key = _first_configured_api_key(settings.vision_api_key, settings.llm_api_key)
    vision_base_url = settings.vision_base_url or settings.llm_base_url

    async for chunk in call_chat_completion_stream(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        model=settings.vision_model,
        api_key=vision_api_key,
        base_url=vision_base_url,
    ):
        yield chunk
