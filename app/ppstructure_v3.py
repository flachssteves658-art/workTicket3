from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import settings


def safe_filename(filename: str) -> str:
    stem = Path(filename).stem or "upload"
    suffix = Path(filename).suffix.lower()
    safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return f"{safe_stem}_{uuid.uuid4().hex[:8]}{suffix}"


def save_upload_file(src_file, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as buffer:
        shutil.copyfileobj(src_file, buffer)


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    for attr in ("to_dict", "dict"):
        method = getattr(result, attr, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    for attr in ("json", "to_json"):
        method = getattr(result, attr, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, str):
                    return json.loads(value)
            except Exception:
                pass
    return {"repr": repr(result)}


def _read_text_files(folder: Path, suffixes: tuple[str, ...]) -> list[dict[str, str]]:
    if not folder.exists():
        return []
    items: list[dict[str, str]] = []
    for file in sorted(folder.rglob("*")):
        if file.is_file() and file.suffix.lower() in suffixes:
            try:
                items.append(
                    {
                        "name": file.name,
                        "path": str(file),
                        "content": file.read_text(encoding="utf-8", errors="ignore"),
                    }
                )
            except Exception as exc:
                items.append({"name": file.name, "path": str(file), "content": f"[read failed: {exc}]"})
    return items


_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            from paddleocr import PPStructureV3
        except Exception as exc:
            raise RuntimeError(
                "Cannot import PPStructureV3. Please install PaddleOCR 3.x and a compatible paddlepaddle build."
            ) from exc
        _pipeline = PPStructureV3()
    return _pipeline


def run_ppstructure_v3(input_path: Path, output_root: Path) -> dict[str, Any]:
    """Run PaddleOCR PPStructureV3 and collect JSON/Markdown artifacts.

    Heavy imports are kept inside this function so the web app can start even when
    PaddleOCR is not installed yet. The endpoint will return a clear error instead.
    """

    job_dir = output_root / input_path.stem
    json_dir = job_dir / "ppstructure_json"
    markdown_dir = job_dir / "ppstructure_markdown"
    visual_dir = job_dir / "visual"
    output_folders = [json_dir, markdown_dir]
    if settings.ocr_save_visual:
        output_folders.append(visual_dir)
    for folder in output_folders:
        folder.mkdir(parents=True, exist_ok=True)

    timing: dict[str, float | int] = {}
    pipeline_start = time.perf_counter()
    pipeline = _get_pipeline()
    timing["pipeline_load_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 2)

    predict_start = time.perf_counter()
    results = pipeline.predict(input=str(input_path))
    timing["predict_call_ms"] = round((time.perf_counter() - predict_start) * 1000, 2)

    pages: list[dict[str, Any]] = []
    save_json_ms = 0.0
    save_markdown_ms = 0.0
    save_visual_ms = 0.0
    raw_collect_ms = 0.0
    page_loop_start = time.perf_counter()
    for idx, result in enumerate(results, start=1):
        if settings.ocr_save_json and hasattr(result, "save_to_json"):
            started = time.perf_counter()
            result.save_to_json(save_path=str(json_dir))
            save_json_ms += (time.perf_counter() - started) * 1000
        if settings.ocr_save_markdown and hasattr(result, "save_to_markdown"):
            started = time.perf_counter()
            result.save_to_markdown(save_path=str(markdown_dir))
            save_markdown_ms += (time.perf_counter() - started) * 1000
        if settings.ocr_save_visual and hasattr(result, "save_to_img"):
            started = time.perf_counter()
            result.save_to_img(save_path=str(visual_dir))
            save_visual_ms += (time.perf_counter() - started) * 1000

        page: dict[str, Any] = {"page_no": idx}
        if settings.ocr_collect_raw:
            started = time.perf_counter()
            page["raw"] = _result_to_dict(result)
            raw_collect_ms += (time.perf_counter() - started) * 1000
        pages.append(page)

    timing["page_loop_ms"] = round((time.perf_counter() - page_loop_start) * 1000, 2)
    timing["save_json_ms"] = round(save_json_ms, 2)
    timing["save_markdown_ms"] = round(save_markdown_ms, 2)
    timing["save_visual_ms"] = round(save_visual_ms, 2)
    timing["raw_collect_ms"] = round(raw_collect_ms, 2)
    timing["page_count"] = len(pages)

    collect_start = time.perf_counter()
    markdown_files = _read_text_files(markdown_dir, (".md", ".markdown", ".txt"))
    json_files = _read_text_files(json_dir, (".json",))
    timing["read_artifacts_ms"] = round((time.perf_counter() - collect_start) * 1000, 2)

    llm_input_parts: list[str] = []
    for item in markdown_files:
        llm_input_parts.append(f"\n\n## Markdown: {item['name']}\n\n{item['content']}")
    for item in json_files:
        content = item["content"]
        if len(content) > 20000:
            content = content[:20000] + "\n...[truncated]"
        llm_input_parts.append(f"\n\n## JSON: {item['name']}\n\n{content}")

    if not llm_input_parts:
        llm_input_parts.append(json.dumps({"pages": pages}, ensure_ascii=False, indent=2)[:60000])

    return {
        "job_dir": str(job_dir),
        "json_dir": str(json_dir),
        "markdown_dir": str(markdown_dir),
        "visual_dir": str(visual_dir),
        "pages": pages,
        "markdown_files": markdown_files,
        "json_files": json_files,
        "llm_input": "\n".join(llm_input_parts),
        "timing": timing,
    }
