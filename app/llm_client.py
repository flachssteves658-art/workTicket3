from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class LLMConfigError(RuntimeError):
    pass


_API_KEY_PLACEHOLDERS = {
    "replace_with_your_key",
    "replace_with_your_vision_key",
}


def _is_configured_api_key(key: str | None) -> bool:
    value = (key or "").strip()
    return bool(value and value not in _API_KEY_PLACEHOLDERS)


def _first_configured_api_key(*keys: str | None) -> str:
    for key in keys:
        value = (key or "").strip()
        if _is_configured_api_key(value):
            return value
    return ""


def _ensure_configured(*, vision: bool = False) -> None:
    if vision:
        if not _first_configured_api_key(settings.vision_api_key, settings.llm_api_key):
            raise LLMConfigError("VISION_API_KEY is not configured.")
    else:
        if not _is_configured_api_key(settings.llm_api_key):
            raise LLMConfigError("LLM_API_KEY is not configured. Please create .env from .env.example.")


async def call_chat_completion(
    messages: list[dict[str, Any]],
    model: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint and return raw text."""
    key = _first_configured_api_key(api_key, settings.llm_api_key)
    if not key:
        raise LLMConfigError("LLM_API_KEY is not configured. Please create .env from .env.example.")

    url_base = (base_url or settings.llm_base_url).rstrip("/")
    url = f"{url_base}/chat/completions"
    payload = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {json.dumps(data, ensure_ascii=False)[:1000]}") from exc


def image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix, "application/octet-stream")

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def build_work_ticket_messages(ocr_content: str) -> list[dict[str, str]]:
    prompt = f"""
你是一个工作票信息结构化助手。

下面内容来自 PaddleOCR PPStructureV3 对工作票的识别结果，包括 Markdown 结构化内容和
overall_ocr_res.rec_texts 完整纯文本。Markdown 用于理解标题、表格和布局，rec_texts 用于
补充 Markdown 可能遗漏的文字；两部分可能包含重复内容，不要重复提取。

请根据 OCR 内容整理为指定 JSON。

要求：
1. 只输出 JSON，不要输出 Markdown，不要解释。
2. 不要编造信息。
3. 无法确定的字段填 null。
4. 多人、多条安全措施、多条风险点使用数组。
5. 保留关键字段的 OCR 原文证据。
6. 如果字段冲突、模糊或识别质量差，放入 uncertain_fields。
7. 表格内容不要丢失，放入 tables 字段。
8. 必须使用下面的英文键名，不要用中文表头替换键名。ticket_no 保留前导零。
9. station_name 是变电站名称；work_location 是具体工作地点或地段，二者不能混淆。
10. 必须单独提取顶层 work_location。无论原表格使用“工作地点”“工作地点或地段”“工作地点或设备”“工作地点及设备双重名称”等哪一种表头，都要提取其每一行的地点值。
11. 如果地点分散在“工作任务”表格或 work_tasks 数组中，必须按原顺序去重，用中文分号“；”连接后写入顶层 work_location；不能只把地点保留在工作任务明细中。
12. work_location 只填写工作区域名称。对于“区域：设备或具体位置”格式，取第一个中文或英文冒号前的区域；不要混入设备详情和工作内容。只要 OCR 中存在明确地点，work_location 就不能为 null。
13. 示例：若两行“工作地点及设备双重名称”分别为“1000kV设备区：室外场地处”和“主变及无功补偿设备区：室外场地处”，则必须输出 "work_location": "1000kV设备区；主变及无功补偿设备区"。
14. 如果 Markdown 中缺少某个字段，但 rec_texts 中存在该字段，必须结合上下文提取。两者内容冲突或无法确定时，放入 uncertain_fields。

目标 JSON：

{{
  "ticket_type": null,
  "ticket_no": null,
  "work_unit": null,
  "work_team": null,
  "work_leader": null,
  "work_members": [],
  "station_name": null,
  "work_location": null,
  "work_content": null,
  "planned_start_time": null,
  "planned_end_time": null,
  "actual_start_time": null,
  "actual_end_time": null,
  "safety_measures": [],
  "risk_points": [],
  "power_outage_scope": null,
  "grounding_measures": [],
  "permit_person": null,
  "issuer": null,
  "approver": null,
  "guardian": null,
  "signatures": [],
  "remarks": null,
  "tables": [],
  "uncertain_fields": [],
  "source_evidence": {{}}
}}

OCR 内容如下：

{ocr_content}
""".strip()

    return [
            {"role": "system", "content": "你擅长从中文工作票 OCR 结果中抽取可靠的结构化字段。"},
            {"role": "user", "content": prompt},
        ]


async def extract_work_ticket(markdown_and_json: str) -> str:
    return await call_chat_completion(
        messages=build_work_ticket_messages(markdown_and_json),
        model=settings.llm_model,
    )


async def direct_vision_extract(image_path: Path, prompt: str | None = None) -> str:
    """Send one image directly to a multimodal LLM and return whatever the model says."""
    _ensure_configured(vision=True)

    user_prompt = prompt or "请直接识别这张图片中的内容，并输出你认为合适的结果。不要额外遵循任何结构限制。"
    data_url = image_to_data_url(image_path)

    vision_key = _first_configured_api_key(settings.vision_api_key, settings.llm_api_key)
    vision_base = settings.vision_base_url or settings.llm_base_url

    return await call_chat_completion(
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
        api_key=vision_key,
        base_url=vision_base,
    )
