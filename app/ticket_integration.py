from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


FIELD_LABELS = {
    "ticket_no": ("TicketNo", "TICKET_NO"),
    "ticket_type": ("TicketType", "TICKET_TYPE"),
    "work_unit": ("WorkUnit", "ORGANIZATION"),
    "work_team": ("WorkTeam", "ORGANIZATION"),
    "work_leader": ("WorkLeader", "PERSON"),
    "work_members": ("WorkMember", "PERSON"),
    "work_location": ("Location", "LOCATION"),
    "work_content": ("WorkContent", "WORK_CONTENT"),
    "planned_start_time": ("PlannedStartTime", "TIME"),
    "planned_end_time": ("PlannedEndTime", "TIME"),
    "actual_start_time": ("ActualStartTime", "TIME"),
    "actual_end_time": ("ActualEndTime", "TIME"),
    "safety_measures": ("SafetyMeasure", "SAFETY_MEASURE"),
    "risk_points": ("RiskPoint", "RISK_POINT"),
    "power_outage_scope": ("PowerOutageScope", "EQUIPMENT_SCOPE"),
    "grounding_measures": ("GroundingMeasure", "SAFETY_MEASURE"),
    "permit_person": ("PermitPerson", "PERSON"),
    "issuer": ("Issuer", "PERSON"),
    "approver": ("Approver", "PERSON"),
    "guardian": ("Guardian", "PERSON"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_values(item))
        return result
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False)]
    text = str(value).strip()
    return [text] if text else []


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value).strip("._")
    return cleaned[:120] or "unnamed_ticket"


def normalize_ticket_fields(parsed: object | None) -> dict[str, Any]:
    """Preserve source fields while adapting Chinese form labels to the API schema."""
    data = dict(parsed) if isinstance(parsed, dict) else {}
    aliases = {
        "ticket_no": ("编号", "工作票编号"),
        "ticket_type": ("工作票类型",),
        "work_unit": ("单位", "工作单位"),
        "work_team": ("班组",),
        "work_leader": ("工作负责人（监护人）", "工作负责人"),
        "work_members": ("工作班人员（不包括工作负责人）", "工作班人员"),
        "station_name": ("变电站名称", "工作的变、配电站名称及设备双重名称", "site_name"),
        "work_location": ("工作地点或地段", "工作地点"),
        "work_content": ("工作内容",),
        "safety_measures": ("注意事项（安全措施）", "安全措施"),
    }
    for field, names in aliases.items():
        if not _values(data.get(field)):
            for name in names:
                if _values(data.get(name)):
                    data[field] = data[name]
                    break

    tasks = data.get("工作任务", [])
    if isinstance(tasks, dict):
        tasks = [tasks]
    if isinstance(tasks, list):
        for field, source in (("work_location", "工作地点或地段"), ("work_content", "工作内容")):
            if not _values(data.get(field)):
                values = [text for task in tasks if isinstance(task, dict)
                          for text in _values(task.get(source))]
                if values:
                    data[field] = "；".join(dict.fromkeys(values))
    return data


def build_ticket_record(parsed: object | None, input_file: str, fallback_id: str) -> dict[str, Any]:
    data = normalize_ticket_fields(parsed)
    uncertain = set(_values(data.get("uncertain_fields")))
    ticket_no = next(iter(_values(data.get("ticket_no"))), "")
    ticket_id = ticket_no or fallback_id
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []

    for field, (label, entity_type) in FIELD_LABELS.items():
        for index, text in enumerate(_values(data.get(field))):
            entity_id = f"{field}:{index + 1}"
            confidence = 0.5 if field in uncertain else 1.0
            entities.append(
                {
                    "id": entity_id,
                    "field": field,
                    "text": text,
                    "label": label,
                    "type": entity_type,
                    "confidence": confidence,
                }
            )
            relationships.append(
                {
                    "source": ticket_id,
                    "target": entity_id,
                    "type": f"HAS_{entity_type}",
                }
            )

    return {
        "ticket_id": ticket_id,
        "ticket_no": ticket_no or None,
        "site_name": next(iter(_values(data.get("station_name"))), None)
        or next(iter(_values(data.get("work_location"))), None),
        "planned_start_time": next(iter(_values(data.get("planned_start_time"))), None),
        "planned_end_time": next(iter(_values(data.get("planned_end_time"))), None),
        "structured_data": data,
        "entities": entities,
        "relationships": relationships,
        "source_file": input_file,
        "created_at": _now_iso(),
    }


def save_ticket_record(record: dict[str, Any]) -> Path:
    settings.ticket_store_dir.mkdir(parents=True, exist_ok=True)
    path = settings.ticket_store_dir / f"{_safe_id(str(record['ticket_id']))}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_ticket_record(ticket_no: str) -> dict[str, Any] | None:
    path = settings.ticket_store_dir / f"{_safe_id(ticket_no)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_ticket_records() -> list[dict[str, Any]]:
    settings.ticket_store_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(settings.ticket_store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return records


async def sync_ticket_to_site(record: dict[str, Any], site_name: str | None = None) -> dict[str, Any]:
    target_site = (site_name or record.get("site_name") or "").strip()
    if not target_site:
        return {"ok": False, "skipped": True, "message": "缺少工地/站点名称"}
    if not settings.hazard_integration_token:
        return {"ok": False, "skipped": True, "message": "未配置 HAZARD_INTEGRATION_TOKEN"}

    data = record.get("structured_data", {})
    payload = {
        "site_name": target_site,
        "ticket_no": record.get("ticket_no") or record.get("ticket_id"),
        "work_content": data.get("work_content"),
        "work_location": data.get("work_location"),
        "planned_start_time": data.get("planned_start_time"),
        "planned_end_time": data.get("planned_end_time"),
        "work_leader": data.get("work_leader"),
        "work_members": data.get("work_members"),
        "safety_measures": data.get("safety_measures"),
        "risk_points": data.get("risk_points"),
    }
    url = f"{settings.hazard_dbm_base_url}/apply_ticket_to_site"
    try:
        async with httpx.AsyncClient(timeout=settings.integration_timeout_seconds) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"X-Integration-Token": settings.hazard_integration_token},
            )
            response.raise_for_status()
        return {"ok": True, "site_name": target_site, "url": url, "response": response.json()}
    except Exception as exc:
        return {"ok": False, "site_name": target_site, "url": url, "message": str(exc)}


def build_local_violation_report(record: dict[str, Any], violation: dict[str, Any]) -> dict[str, Any]:
    data = record.get("structured_data", {})
    risk_points = _values(data.get("risk_points"))
    measures = _values(data.get("safety_measures")) + _values(data.get("grounding_measures"))
    return {
        "report_type": "work_ticket_violation_report",
        "generated_at": _now_iso(),
        "ticket_no": record.get("ticket_no") or record.get("ticket_id"),
        "work_location": data.get("work_location"),
        "work_content": data.get("work_content"),
        "work_leader": data.get("work_leader"),
        "violation": violation,
        "ticket_risk_points": risk_points,
        "required_safety_measures": measures,
        "conclusion": "检测到的违章需结合工作票风险点和安全措施进行人工复核。",
        "recommended_actions": [
            "立即核对现场人员、地点和作业内容是否与工作票一致",
            "复核对应安全措施是否已执行",
            "保存摄像头截图、检测时间和工作票编号作为处置证据",
        ],
    }
