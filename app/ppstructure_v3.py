from __future__ import annotations

import json
import os
import shutil
import threading
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


def _print_rec_texts(json_files: list[dict[str, str]]) -> None:
    """Print each page's raw OCR text so it can be inspected in backend logs."""
    total_lines = 0
    total_chars = 0
    for item in json_files:
        try:
            ocr_json = json.loads(item["content"])
            rec_texts = ocr_json.get("overall_ocr_res", {}).get("rec_texts", [])
            if not isinstance(rec_texts, list):
                rec_texts = []
            rec_texts = [str(text) for text in rec_texts]
            ocr_text = "\n".join(rec_texts)
            total_lines += len(rec_texts)
            total_chars += len(ocr_text)
            print(
                f"\n[OCR rec_texts] file={item['path']} "
                f"lines={len(rec_texts)} chars={len(ocr_text)}\n"
                f"{ocr_text}\n"
                "[OCR rec_texts end]",
                flush=True,
            )
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            print(
                f"[OCR rec_texts] 无法读取 {item['path']}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
    print(
        f"[OCR rec_texts summary] files={len(json_files)} "
        f"lines={total_lines} chars={total_chars}",
        flush=True,
    )


def _extract_rec_texts_files(json_files: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Extract compact plain text from saved PPStructure JSON artifacts."""
    items: list[dict[str, Any]] = []
    for item in json_files:
        try:
            ocr_json = json.loads(item["content"])
            rec_texts = ocr_json.get("overall_ocr_res", {}).get("rec_texts", [])
            if not isinstance(rec_texts, list):
                rec_texts = []
            lines = [str(text).strip() for text in rec_texts if str(text).strip()]
            items.append(
                {
                    "name": item["name"],
                    "path": item["path"],
                    "lines": lines,
                    "content": "\n".join(lines),
                }
            )
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return items


_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        # Paddle's oneDNN path is unstable on some Windows CPU/Python builds.
        # Set these before importing PaddleOCR so the native runtime sees them.
        if not settings.ocr_enable_mkldnn:
            os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("OMP_NUM_THREADS", str(settings.ocr_cpu_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(settings.ocr_cpu_threads))
        try:
            from paddleocr import PPStructureV3
        except Exception as exc:
            raise RuntimeError(
                "Cannot import PPStructureV3. Please install PaddleOCR 3.x and a compatible paddlepaddle build."
            ) from exc
        _pipeline = PPStructureV3(
            device=settings.ocr_device,
            enable_mkldnn=settings.ocr_enable_mkldnn,
            cpu_threads=settings.ocr_cpu_threads,
            text_detection_model_name=settings.ocr_text_detection_model,
            text_recognition_model_name=settings.ocr_text_recognition_model,
            use_doc_orientation_classify=settings.ocr_use_doc_orientation,
            use_doc_unwarping=settings.ocr_use_doc_unwarping,
            use_textline_orientation=settings.ocr_use_textline_orientation,
            use_formula_recognition=settings.ocr_use_formula_recognition,
            use_chart_recognition=settings.ocr_use_chart_recognition,
            use_seal_recognition=settings.ocr_use_seal_recognition,
        )
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
    # Paddle predictors are not thread-safe. Serialize inference and materialize
    # the generator here so predict_call_ms measures the real native inference.
    with _pipeline_lock:
        results = list(pipeline.predict(input=str(input_path)))
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

    _print_rec_texts(json_files)
    rec_text_files = _extract_rec_texts_files(json_files)

    llm_input_parts: list[str] = []
    for item in markdown_files:
        llm_input_parts.append(f"\n\n## Markdown: {item['name']}\n\n{item['content']}")
    for item in rec_text_files:
        if item["content"]:
            llm_input_parts.append(
                f"\n\n## OCR完整纯文本（rec_texts）: {item['name']}\n\n{item['content']}"
            )
    if not llm_input_parts:
        raise RuntimeError("OCR 未生成 Markdown 或 rec_texts 文本，无法进行大模型抽取。")

    return {
        "job_dir": str(job_dir),
        "json_dir": str(json_dir),
        "markdown_dir": str(markdown_dir),
        "visual_dir": str(visual_dir),
        "pages": pages,
        "markdown_files": markdown_files,
        "json_files": json_files,
        "rec_text_files": rec_text_files,
        "llm_input": "\n".join(llm_input_parts),
        "timing": timing,
    }
