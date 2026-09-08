from __future__ import annotations

import hmac
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import ROOT_DIR, settings
from app.llm_client import LLMConfigError, direct_vision_extract, extract_work_ticket, image_to_data_url
from app.llm_stream import (
    call_chat_completion_stream,
    extract_work_ticket_stream,
    direct_vision_extract_stream,
)
from app.ppstructure_v3 import run_ppstructure_v3, safe_filename, save_upload_file
from app.asset_database_client import (
    bind_camera_streams,
    cancel_detection_task as cancel_detection_task_remote,
    catalog_status,
    confirm_cameras,
    import_catalogs,
    list_stream_options,
    load_detection_task,
    load_match_result,
    match_ticket_assets,
)
from app.ticket_integration import (
    build_local_violation_report,
    build_ticket_record,
    load_ticket_record,
    save_ticket_record,
    sync_ticket_to_site,
)


app = FastAPI(title="Work Ticket OCR", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = ROOT_DIR / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _try_parse_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except Exception:
        pass

    fenced = re.search(r"\`\`\`(?:json)?\s*([\s\S]*?)\s*\`\`\`", text, re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _elapsed_ms(start: float, end: float | None = None) -> float:
    return round(((end or time.perf_counter()) - start) * 1000, 2)


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _archive_ticket(parsed_json: object | None, input_path: Path, job_dir: str) -> dict[str, object]:
    record = build_ticket_record(parsed_json, str(input_path), Path(job_dir).name)
    try:
        asset_matching = await match_ticket_assets(record)
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        asset_matching = {
            "status": (
                "match_conflict"
                if exc.response.status_code == 409
                else "database_unavailable"
            ),
            "storage": "mysql",
            "message": detail,
        }
    except Exception as exc:
        asset_matching = {
            "status": "database_unavailable",
            "storage": "mysql",
            "message": str(exc),
        }
    record["asset_matching"] = asset_matching
    record_path = save_ticket_record(record)
    return {
        "ticket_record": record,
        "ticket_record_path": str(record_path),
        "asset_matching": asset_matching,
    }


def _require_integration_token(token: str | None) -> None:
    if not settings.hazard_integration_token:
        raise HTTPException(status_code=503, detail="服务端尚未配置 HAZARD_INTEGRATION_TOKEN")
    if not token or not hmac.compare_digest(token, settings.hazard_integration_token):
        raise HTTPException(status_code=401, detail="无效的集成令牌")


def _raise_upstream_error(exc: httpx.HTTPError) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            payload = exc.response.json()
            detail = payload.get("detail", str(exc))
        except Exception:
            detail = str(exc)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        ) from exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


class TicketSyncRequest(BaseModel):
    ticket_no: str
    site_name: str | None = None


class ViolationReportRequest(BaseModel):
    ticket_no: str
    violation: dict[str, object] = Field(default_factory=dict)


class CameraConfirmationRequest(BaseModel):
    camera_ids: list[str] = Field(min_length=1)


class CameraStreamBinding(BaseModel):
    camera_id: str = Field(min_length=1, max_length=80)
    stream_config_id: int | None = Field(default=None, ge=1)


class CameraStreamBindingRequest(BaseModel):
    bindings: list[CameraStreamBinding] = Field(min_length=1)
    allow_station_mismatch: bool = False


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "llm_configured": bool(settings.llm_api_key and settings.llm_api_key != "replace_with_your_key"),
        "upload_dir": str(settings.upload_dir),
        "output_dir": str(settings.output_dir),
        "ticket_store_dir": str(settings.ticket_store_dir),
        "hazard_sync_configured": bool(settings.hazard_integration_token),
        "asset_catalog": await catalog_status(),
        "config_debug": {
            "llm_api_key_configured": bool(settings.llm_api_key),
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "vision_api_key_configured": bool(settings.vision_api_key),
            "vision_base_url": settings.vision_base_url,
            "vision_model": settings.vision_model,
            "llm_timeout_seconds": settings.llm_timeout_seconds,
        }
    }


@app.get("/api/catalog/status")
async def asset_catalog_status() -> dict[str, object]:
    return await catalog_status()


@app.post("/api/catalog/import")
async def import_asset_catalog(
    camera_file: Annotated[UploadFile, File(...)],
    equipment_file: Annotated[UploadFile, File(...)],
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    import_dir = settings.catalog_dir / "_imports" / uuid4().hex
    import_dir.mkdir(parents=True, exist_ok=True)
    camera_path = import_dir / safe_filename(camera_file.filename or "cameras.xlsx")
    equipment_path = import_dir / safe_filename(equipment_file.filename or "equipment.xls")
    try:
        save_upload_file(camera_file.file, camera_path)
        save_upload_file(equipment_file.file, equipment_path)
        result = await import_catalogs(camera_path, equipment_path)
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await camera_file.close()
        await equipment_file.close()
        camera_path.unlink(missing_ok=True)
        equipment_path.unlink(missing_ok=True)
        import_dir.rmdir()
    return {"success": True, **result}


@app.post("/api/recognize-structure")
async def recognize_structure(file: Annotated[UploadFile, File(...)]) -> dict[str, object]:
    filename = safe_filename(file.filename or "work_ticket")
    input_path = settings.upload_dir / filename

    try:
        save_upload_file(file.file, input_path)
    finally:
        await file.close()

    try:
        ocr_result = run_ppstructure_v3(input_path, settings.output_dir)
        llm_output = await extract_work_ticket(ocr_result["llm_input"])
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    parsed_json = _try_parse_json(llm_output)
    integration = await _archive_ticket(parsed_json, input_path, ocr_result["job_dir"])

    result_path = Path(ocr_result["job_dir"]) / "llm_result.json"
    result_path.write_text(
        json.dumps(
            {
                "input_file": str(input_path),
                "llm_output": llm_output,
                "parsed_json": parsed_json,
                **integration,
                "ocr_artifacts": {
                    "job_dir": ocr_result["job_dir"],
                    "json_dir": ocr_result["json_dir"],
                    "markdown_dir": ocr_result["markdown_dir"],
                    "visual_dir": ocr_result["visual_dir"],
                    "timing": ocr_result.get("timing", {}),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "input_file": str(input_path),
        "ocr_artifacts": {
            "job_dir": ocr_result["job_dir"],
            "json_dir": ocr_result["json_dir"],
            "markdown_dir": ocr_result["markdown_dir"],
            "visual_dir": ocr_result["visual_dir"],
        },
        "markdown_files": [
            {"name": item["name"], "path": item["path"], "preview": item["content"][:2000]}
            for item in ocr_result["markdown_files"]
        ],
        "llm_output": llm_output,
        "parsed_json": parsed_json,
        **integration,
        "result_path": str(result_path),
    }


@app.post("/api/direct-vision")
async def direct_vision(
    file: Annotated[UploadFile, File(...)],
    prompt: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        raise HTTPException(status_code=400, detail="Direct vision mode only accepts image files.")

    filename = safe_filename(file.filename or "image")
    input_path = settings.upload_dir / filename

    try:
        save_upload_file(file.file, input_path)
    finally:
        await file.close()

    try:
        llm_output = await direct_vision_extract(input_path, prompt)
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] direct_vision_extract failed: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Vision extraction failed: {str(exc)}\n{error_trace}") from exc

    return {
        "input_file": str(input_path),
        "llm_output": llm_output,
    }


# ============================================================================
# Streaming endpoints - 流式端点，一边生成一边输出
# ============================================================================


@app.post("/api/recognize-structure-stream")
async def recognize_structure_stream(file: Annotated[UploadFile, File(...)]) -> StreamingResponse:
    """Stream OCR and LLM output with step timing."""
    request_started_at = _utc_now_iso()
    request_start = time.perf_counter()
    filename = safe_filename(file.filename or "work_ticket")
    input_path = settings.upload_dir / filename

    upload_start = time.perf_counter()
    try:
        save_upload_file(file.file, input_path)
    finally:
        await file.close()
    upload_ms = _elapsed_ms(upload_start)

    async def stream_generator():
        """Generate SSE output with step timing."""
        timings: dict[str, object] = {
            "request_started_at": request_started_at,
            "upload_ms": upload_ms,
        }
        try:
            yield _sse(
                {
                    "type": "step_complete",
                    "step": "upload",
                    "label": "文件接收",
                    "elapsed_ms": upload_ms,
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "ended_at": _utc_now_iso(),
                }
            )

            ocr_start = time.perf_counter()
            yield _sse(
                {
                    "type": "step_start",
                    "step": "ocr",
                    "label": "OCR 识别",
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "started_at": _utc_now_iso(),
                }
            )
            ocr_result = run_ppstructure_v3(input_path, settings.output_dir)
            ocr_ms = _elapsed_ms(ocr_start)
            timings["ocr_ms"] = ocr_ms
            timings["ocr_detail"] = ocr_result.get("timing", {})

            ocr_info = {
                "input_file": str(input_path),
                "ocr_artifacts": {
                    "job_dir": ocr_result["job_dir"],
                    "json_dir": ocr_result["json_dir"],
                    "markdown_dir": ocr_result["markdown_dir"],
                    "visual_dir": ocr_result["visual_dir"],
                    "timing": ocr_result.get("timing", {}),
                },
                "markdown_files": [
                    {"name": item["name"], "path": item["path"], "preview": item["content"][:2000]}
                    for item in ocr_result["markdown_files"]
                ],
            }
            yield _sse(
                {
                    "type": "step_complete",
                    "step": "ocr",
                    "label": "OCR 识别",
                    "elapsed_ms": ocr_ms,
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "ended_at": _utc_now_iso(),
                }
            )
            yield _sse({"type": "ocr_complete", "data": ocr_info, "timing": dict(timings)})

            llm_output_chunks = []
            llm_wait_start = time.perf_counter()
            generation_start: float | None = None
            first_token_ms: float | None = None
            yield _sse(
                {
                    "type": "step_start",
                    "step": "llm_wait",
                    "label": "等待大模型首字",
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "started_at": _utc_now_iso(),
                }
            )
            async for chunk in extract_work_ticket_stream(ocr_result["llm_input"]):
                if first_token_ms is None:
                    first_token_ms = _elapsed_ms(llm_wait_start)
                    generation_start = time.perf_counter()
                    timings["llm_first_token_ms"] = first_token_ms
                    timings["llm_first_token_total_elapsed_ms"] = _elapsed_ms(request_start)
                    yield _sse(
                        {
                            "type": "step_complete",
                            "step": "llm_wait",
                            "label": "等待大模型首字",
                            "elapsed_ms": first_token_ms,
                            "total_elapsed_ms": timings["llm_first_token_total_elapsed_ms"],
                            "ended_at": _utc_now_iso(),
                        }
                    )
                    yield _sse(
                        {
                            "type": "first_token",
                            "step": "llm_wait",
                            "label": "大模型首字返回",
                            "elapsed_ms": first_token_ms,
                            "total_elapsed_ms": timings["llm_first_token_total_elapsed_ms"],
                            "received_at": _utc_now_iso(),
                        }
                    )
                    yield _sse(
                        {
                            "type": "step_start",
                            "step": "llm_stream",
                            "label": "大模型生成",
                            "total_elapsed_ms": _elapsed_ms(request_start),
                            "started_at": _utc_now_iso(),
                        }
                    )
                llm_output_chunks.append(chunk)
                yield _sse({"type": "llm_chunk", "data": chunk})

            llm_ms = _elapsed_ms(generation_start) if generation_start is not None else 0
            timings["llm_stream_ms"] = llm_ms
            timings["llm_first_token_ms"] = first_token_ms

            llm_output = "".join(llm_output_chunks)
            parsed_json = _try_parse_json(llm_output)
            integration = await _archive_ticket(parsed_json, input_path, ocr_result["job_dir"])
            result_path = Path(ocr_result["job_dir"]) / "llm_result.json"
            total_ms = _elapsed_ms(request_start)
            request_ended_at = _utc_now_iso()
            timings.update(
                {
                    "total_ms": total_ms,
                    "request_ended_at": request_ended_at,
                }
            )
            result_path.write_text(
                json.dumps(
                    {
                        "input_file": str(input_path),
                        "llm_output": llm_output,
                        "parsed_json": parsed_json,
                        **integration,
                        "ocr_artifacts": ocr_info["ocr_artifacts"],
                        "timing": timings,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            yield _sse(
                {
                    "type": "step_complete",
                    "step": "llm_stream",
                    "label": "大模型生成",
                    "elapsed_ms": llm_ms,
                    "first_token_ms": first_token_ms,
                    "total_elapsed_ms": total_ms,
                    "ended_at": request_ended_at,
                }
            )
            yield _sse(
                {
                    "type": "complete",
                    "llm_output": llm_output,
                    "parsed_json": parsed_json,
                    **integration,
                    "result_path": str(result_path),
                    "timing": timings,
                }
            )

        except LLMConfigError as exc:
            timings["total_ms"] = _elapsed_ms(request_start)
            timings["request_ended_at"] = _utc_now_iso()
            yield _sse({"type": "error", "error": str(exc), "timing": timings})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            timings["total_ms"] = _elapsed_ms(request_start)
            timings["request_ended_at"] = _utc_now_iso()
            yield _sse(
                {
                    "type": "error",
                    "error": f"Structure extraction failed: {str(exc)}",
                    "timing": timings,
                }
            )

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


# Authenticated compatibility API for the original ticket/hazard integration.
@app.post("/api/v1/parse_ticket")
async def parse_ticket_compat(
    file: Annotated[UploadFile, File(...)],
    x_integration_token: Annotated[str | None, Header()] = None,
    enable_hazard_sync: bool = False,
    hazard_site_name: str | None = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    result = await recognize_structure(file)
    record = result["ticket_record"]
    sync_result = await sync_ticket_to_site(record, hazard_site_name) if enable_hazard_sync else None
    return {
        "success": True,
        "ticket_id": record["ticket_id"],
        "ticket_no": record["ticket_no"],
        "entities": record["entities"],
        "relationships": record["relationships"],
        "structured_data": record["structured_data"],
        "hazard_sync": sync_result,
        "result_path": result["result_path"],
    }


@app.get("/api/v1/tickets/{ticket_no}")
async def ticket_detail(
    ticket_no: str,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    record = load_ticket_record(ticket_no)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该工作票")
    return record


@app.post("/api/v1/tickets/{ticket_no}/match-assets")
async def rematch_ticket_assets(
    ticket_no: str,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    record = load_ticket_record(ticket_no)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该工作票")
    result = await match_ticket_assets(record)
    record["asset_matching"] = result
    save_ticket_record(record)
    return result


@app.get("/api/v1/tickets/{ticket_no}/asset-matches")
async def ticket_asset_matches(
    ticket_no: str,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    result = await load_match_result(ticket_no)
    if result is None:
        raise HTTPException(status_code=404, detail="尚未生成设备和摄像头匹配结果")
    return result


@app.post("/api/v1/tickets/{ticket_no}/confirm-cameras")
async def confirm_ticket_cameras(
    ticket_no: str,
    request: CameraConfirmationRequest,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    try:
        task = await confirm_cameras(ticket_no, request.camera_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)
    return {"success": True, "detection_task": task}


@app.get("/api/v1/stream-options")
async def stream_options(
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    try:
        return await list_stream_options()
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)


@app.post("/api/v1/cameras/bind-streams")
async def bind_ticket_camera_streams(
    request: CameraStreamBindingRequest,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    try:
        return await bind_camera_streams(
            [binding.model_dump() for binding in request.bindings],
            request.allow_station_mismatch,
        )
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)


@app.get("/api/v1/tickets/{ticket_no}/detection-task")
async def ticket_detection_task(
    ticket_no: str,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    try:
        task = await load_detection_task(ticket_no)
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)
    if task is None:
        raise HTTPException(status_code=404, detail="尚未生成AI检测任务")
    return task


@app.post("/api/v1/tickets/{ticket_no}/cancel-detection-task")
async def cancel_ticket_detection_task(
    ticket_no: str,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    try:
        task = await cancel_detection_task_remote(ticket_no)
    except httpx.HTTPError as exc:
        _raise_upstream_error(exc)
    if task is None:
        raise HTTPException(status_code=404, detail="尚未生成AI检测任务")
    return {"success": True, "detection_task": task}


@app.post("/api/v1/apply_ticket_to_site")
async def apply_ticket_to_site(
    request: TicketSyncRequest,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    record = load_ticket_record(request.ticket_no)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该工作票，请先完成识别")
    result = await sync_ticket_to_site(record, request.site_name)
    if not result.get("ok") and not result.get("skipped"):
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/api/v1/generate_violation_report")
async def generate_violation_report(
    request: ViolationReportRequest,
    x_integration_token: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_integration_token(x_integration_token)
    record = load_ticket_record(request.ticket_no)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该工作票，请先完成识别")
    return {"success": True, "report": build_local_violation_report(record, request.violation)}


@app.post("/api/direct-vision-stream")
async def direct_vision_stream(
    file: Annotated[UploadFile, File(...)],
    prompt: Annotated[str | None, Form()] = None,
) -> StreamingResponse:
    """Stream vision model output with step timing."""
    request_started_at = _utc_now_iso()
    request_start = time.perf_counter()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        raise HTTPException(status_code=400, detail="Direct vision mode only accepts image files.")

    filename = safe_filename(file.filename or "image")
    input_path = settings.upload_dir / filename

    upload_start = time.perf_counter()
    try:
        save_upload_file(file.file, input_path)
    finally:
        await file.close()
    upload_ms = _elapsed_ms(upload_start)

    async def stream_generator():
        """Generate SSE output with step timing."""
        timings: dict[str, object] = {
            "request_started_at": request_started_at,
            "upload_ms": upload_ms,
        }
        try:
            yield _sse(
                {
                    "type": "step_complete",
                    "step": "upload",
                    "label": "文件接收",
                    "elapsed_ms": upload_ms,
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "ended_at": _utc_now_iso(),
                }
            )

            encode_start = time.perf_counter()
            yield _sse(
                {
                    "type": "step_start",
                    "step": "image_encode",
                    "label": "图片编码",
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "started_at": _utc_now_iso(),
                }
            )
            data_url = image_to_data_url(input_path)
            image_encode_ms = _elapsed_ms(encode_start)
            timings["image_encode_ms"] = image_encode_ms
            yield _sse(
                {
                    "type": "step_complete",
                    "step": "image_encode",
                    "label": "图片编码",
                    "elapsed_ms": image_encode_ms,
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "ended_at": _utc_now_iso(),
                }
            )

            user_prompt = prompt or "请直接识别这张图片中的内容，并输出你认为合适的结果。"
            vision_api_key = settings.vision_api_key or settings.llm_api_key
            vision_base_url = settings.vision_base_url or settings.llm_base_url

            llm_wait_start = time.perf_counter()
            generation_start: float | None = None
            first_token_ms: float | None = None
            yield _sse(
                {
                    "type": "step_start",
                    "step": "llm_wait",
                    "label": "等待大模型首字",
                    "total_elapsed_ms": _elapsed_ms(request_start),
                    "started_at": _utc_now_iso(),
                }
            )
            llm_output_chunks = []
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
                if first_token_ms is None:
                    first_token_ms = _elapsed_ms(llm_wait_start)
                    generation_start = time.perf_counter()
                    timings["llm_first_token_ms"] = first_token_ms
                    timings["llm_first_token_total_elapsed_ms"] = _elapsed_ms(request_start)
                    yield _sse(
                        {
                            "type": "step_complete",
                            "step": "llm_wait",
                            "label": "等待大模型首字",
                            "elapsed_ms": first_token_ms,
                            "total_elapsed_ms": timings["llm_first_token_total_elapsed_ms"],
                            "ended_at": _utc_now_iso(),
                        }
                    )
                    yield _sse(
                        {
                            "type": "first_token",
                            "step": "llm_wait",
                            "label": "视觉大模型首字返回",
                            "elapsed_ms": first_token_ms,
                            "total_elapsed_ms": timings["llm_first_token_total_elapsed_ms"],
                            "received_at": _utc_now_iso(),
                        }
                    )
                    yield _sse(
                        {
                            "type": "step_start",
                            "step": "vision_stream",
                            "label": "视觉大模型生成",
                            "total_elapsed_ms": _elapsed_ms(request_start),
                            "started_at": _utc_now_iso(),
                        }
                    )
                llm_output_chunks.append(chunk)
                yield _sse({"type": "chunk", "data": chunk})

            llm_output = "".join(llm_output_chunks)
            llm_generation_ms = _elapsed_ms(generation_start) if generation_start is not None else 0
            total_ms = _elapsed_ms(request_start)
            request_ended_at = _utc_now_iso()
            timings.update(
                {
                    "llm_stream_ms": llm_generation_ms,
                    "llm_first_token_ms": first_token_ms,
                    "total_ms": total_ms,
                    "request_ended_at": request_ended_at,
                }
            )
            yield _sse(
                {
                    "type": "step_complete",
                    "step": "vision_stream",
                    "label": "视觉大模型生成",
                    "elapsed_ms": llm_generation_ms,
                    "first_token_ms": first_token_ms,
                    "total_elapsed_ms": total_ms,
                    "ended_at": request_ended_at,
                }
            )
            yield _sse(
                {
                    "type": "complete",
                    "input_file": str(input_path),
                    "llm_output": llm_output,
                    "timing": timings,
                }
            )

        except LLMConfigError as exc:
            timings["total_ms"] = _elapsed_ms(request_start)
            timings["request_ended_at"] = _utc_now_iso()
            yield _sse({"type": "error", "error": str(exc), "timing": timings})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            timings["total_ms"] = _elapsed_ms(request_start)
            timings["request_ended_at"] = _utc_now_iso()
            yield _sse(
                {
                    "type": "error",
                    "error": f"Vision extraction failed: {str(exc)}",
                    "timing": timings,
                }
            )

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
