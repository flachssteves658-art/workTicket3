#!/usr/bin/env python3
"""Debug script to test API configuration."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings

print("=" * 60)
print("API Configuration Debug")
print("=" * 60)

print("\n[LLM Configuration]")
print(f"  LLM_API_KEY: {settings.llm_api_key[:20]}...")
print(f"  LLM_BASE_URL: {settings.llm_base_url}")
print(f"  LLM_MODEL: {settings.llm_model}")
print(f"  LLM_TIMEOUT: {settings.llm_timeout_seconds}s")

print("\n[Vision Configuration]")
print(f"  VISION_API_KEY: {settings.vision_api_key[:20] if settings.vision_api_key else 'NOT_SET'}...")
print(f"  VISION_BASE_URL: {settings.vision_base_url}")
print(f"  VISION_MODEL: {settings.vision_model}")

print("\n[Analysis]")
if "{" in settings.vision_base_url or "}" in settings.vision_base_url:
    print("  ⚠️  WARNING: VISION_BASE_URL contains braces - likely a placeholder!")
    print(f"      Current value: {settings.vision_base_url}")
    print("      Please replace placeholder with actual API endpoint")
else:
    print("  ✓ VISION_BASE_URL looks valid")

if not settings.vision_api_key:
    print("  ⚠️  WARNING: VISION_API_KEY not set - will fall back to LLM_API_KEY")
elif settings.vision_api_key != settings.llm_api_key:
    print("  ✓ VISION_API_KEY is independently configured")
else:
    print("  ℹ️  VISION_API_KEY same as LLM_API_KEY")

print("\n" + "=" * 60)
