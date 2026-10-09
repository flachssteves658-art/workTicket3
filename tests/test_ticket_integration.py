from app.ticket_integration import build_ticket_record
from app.ticket_integration import normalize_ticket_fields


def test_normalize_work_location_from_english_work_tasks() -> None:
    data = normalize_ticket_fields(
        {
            "work_tasks": [
                {"location_and_equipment": "1000kV1号保护小室：二次设备屏柜前和后"},
                {"location_and_equipment": "自动化机房：二次设备屏柜前和后"},
            ],
        },
    )

    assert data["work_location"] == "1000kV1号保护小室；自动化机房"


def test_build_record_creates_location_entity_from_work_tasks() -> None:
    record = build_ticket_record(
        {"ticket_no": "ticket-1", "work_tasks": [{"location_and_equipment": "通信机房"}]},
        "ticket.pdf",
        "fallback",
    )

    assert record["structured_data"]["work_location"] == "通信机房"
    assert record["site_name"] == "通信机房"
    assert any(entity["type"] == "LOCATION" and entity["text"] == "通信机房" for entity in record["entities"])


def test_normalize_actual_chinese_model_shape() -> None:
    record = build_ticket_record(
        {
            "编号": "变电二票20260723001",
            "变电站名称": "1000kV特高压淮南站",
            "工作任务": [
                {"工作地点及设备双重名称": "1000kV1号保护小室：二次设备屏柜前和后"},
                {"工作地点及设备双重名称": "自动化机房：电力系统相量测量主机屏前和后"},
            ],
            "计划工作时间": {
                "开始": "2026年07月23日08时00分",
                "结束": "2026年07月24日18时00分",
            },
        },
        "ticket.pdf",
        "fallback",
    )

    assert record["ticket_no"] == "变电二票20260723001"
    assert record["site_name"] == "1000kV特高压淮南站"
    assert record["planned_start_time"] == "2026年07月23日08时00分"
    assert record["planned_end_time"] == "2026年07月24日18时00分"
    assert record["structured_data"]["work_location"] == "1000kV1号保护小室；自动化机房"


def test_task_area_overrides_unreliable_model_work_location() -> None:
    data = normalize_ticket_fields(
        {
            "work_location": "模型错误地点",
            "工作任务": [
                {
                    "工作地点及设备双重名称": "1000kV设备区：一次设备处",
                    "工作内容": "一次设备专业巡检",
                },
                {
                    "工作地点及设备双重名称": "主变及无功补偿设备区:室外场地处",
                    "工作内容": "绿化维护、拔草",
                },
            ],
        },
    )

    assert data["work_location"] == "1000kV设备区；主变及无功补偿设备区"


def test_normalize_additional_chinese_heading_variants() -> None:
    data = normalize_ticket_fields(
        {
            "票类型": "国网安徽省电力有限公司变电站第二种工作票",
            "工作的变电站名称": "1000kV特高压淮南站",
            "注意事项安全措施": ["进入指定区域工作"],
        },
    )

    assert data["ticket_type"] == "国网安徽省电力有限公司变电站第二种工作票"
    assert data["station_name"] == "1000kV特高压淮南站"
    assert data["safety_measures"] == ["进入指定区域工作"]
