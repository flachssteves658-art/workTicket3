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
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    upload_dir: Path = ROOT_DIR / os.getenv("UPLOAD_DIR", "storage/uploads")
    output_dir: Path = ROOT_DIR / os.getenv("OUTPUT_DIR", "storage/outputs")

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    vision_api_key: str = os.getenv("VISION_API_KEY", "")
    vision_base_url: str = os.getenv("VISION_BASE_URL", "").rstrip("/")
    vision_model: str = os.getenv("VISION_MODEL", "gpt-4o-mini")

    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

    ocr_save_json: bool = os.getenv("OCR_SAVE_JSON", "1").lower() in {"1", "true", "yes", "on"}
    ocr_save_markdown: bool = os.getenv("OCR_SAVE_MARKDOWN", "1").lower() in {"1", "true", "yes", "on"}
    ocr_save_visual: bool = os.getenv("OCR_SAVE_VISUAL", "0").lower() in {"1", "true", "yes", "on"}
    ocr_collect_raw: bool = os.getenv("OCR_COLLECT_RAW", "0").lower() in {"1", "true", "yes", "on"}


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
