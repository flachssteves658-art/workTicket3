from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8880"))
    upload_dir: Path = ROOT_DIR / os.getenv("UPLOAD_DIR", "storage/uploads")
    output_dir: Path = ROOT_DIR / os.getenv("OUTPUT_DIR", "storage/outputs")
    ticket_store_dir: Path = ROOT_DIR / os.getenv("TICKET_STORE_DIR", "storage/tickets")
    catalog_dir: Path = ROOT_DIR / os.getenv("CATALOG_DIR", "storage/catalog")
    match_dir: Path = ROOT_DIR / os.getenv("MATCH_DIR", "storage/matches")

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    vision_api_key: str = os.getenv("VISION_API_KEY", "")
    vision_base_url: str = os.getenv("VISION_BASE_URL", "").rstrip("/")
    vision_model: str = os.getenv("VISION_MODEL", "gpt-4o-mini")

    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    hazard_dbm_base_url: str = os.getenv("HAZARD_DBM_BASE_URL", "http://127.0.0.1:8005").rstrip("/")
    hazard_integration_token: str = os.getenv("HAZARD_INTEGRATION_TOKEN", "")
    integration_timeout_seconds: int = int(os.getenv("INTEGRATION_TIMEOUT_SECONDS", "15"))

    ocr_save_json: bool = os.getenv("OCR_SAVE_JSON", "1").lower() in {"1", "true", "yes", "on"}
    ocr_save_markdown: bool = os.getenv("OCR_SAVE_MARKDOWN", "1").lower() in {"1", "true", "yes", "on"}
    ocr_save_visual: bool = os.getenv("OCR_SAVE_VISUAL", "0").lower() in {"1", "true", "yes", "on"}
    ocr_collect_raw: bool = os.getenv("OCR_COLLECT_RAW", "0").lower() in {"1", "true", "yes", "on"}
    ocr_device: str = os.getenv("OCR_DEVICE", "cpu")
    ocr_enable_mkldnn: bool = os.getenv("OCR_ENABLE_MKLDNN", "0").lower() in {"1", "true", "yes", "on"}
    ocr_cpu_threads: int = max(1, int(os.getenv("OCR_CPU_THREADS", "1")))
    ocr_text_detection_model: str = os.getenv("OCR_TEXT_DETECTION_MODEL", "PP-OCRv4_mobile_det")
    ocr_text_recognition_model: str = os.getenv("OCR_TEXT_RECOGNITION_MODEL", "PP-OCRv4_mobile_rec")
    ocr_use_doc_orientation: bool = os.getenv("OCR_USE_DOC_ORIENTATION", "0").lower() in {"1", "true", "yes", "on"}
    ocr_use_doc_unwarping: bool = os.getenv("OCR_USE_DOC_UNWARPING", "0").lower() in {"1", "true", "yes", "on"}
    ocr_use_textline_orientation: bool = os.getenv("OCR_USE_TEXTLINE_ORIENTATION", "0").lower() in {"1", "true", "yes", "on"}
    ocr_use_formula_recognition: bool = os.getenv("OCR_USE_FORMULA_RECOGNITION", "0").lower() in {"1", "true", "yes", "on"}
    ocr_use_chart_recognition: bool = os.getenv("OCR_USE_CHART_RECOGNITION", "0").lower() in {"1", "true", "yes", "on"}
    ocr_use_seal_recognition: bool = os.getenv("OCR_USE_SEAL_RECOGNITION", "0").lower() in {"1", "true", "yes", "on"}


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.ticket_store_dir.mkdir(parents=True, exist_ok=True)
settings.catalog_dir.mkdir(parents=True, exist_ok=True)
settings.match_dir.mkdir(parents=True, exist_ok=True)
