from app.llm_client import build_work_ticket_messages


def test_prompt_requires_top_level_work_location_from_task_rows() -> None:
    messages = build_work_ticket_messages("OCR sample")
    prompt = messages[-1]["content"]

    assert "必须单独提取顶层 work_location" in prompt
    assert "工作地点及设备双重名称" in prompt
    assert "不能只把地点保留在工作任务明细中" in prompt
    assert '"work_location": "1000kV设备区；主变及无功补偿设备区"' in prompt
    assert prompt.endswith("OCR sample")
