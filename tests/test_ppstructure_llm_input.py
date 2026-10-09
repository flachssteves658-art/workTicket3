import json

from app.ppstructure_v3 import _extract_rec_texts_files


def test_extract_rec_texts_keeps_text_without_full_json() -> None:
    json_files = [
        {
            "name": "page_0_res.json",
            "path": "page_0_res.json",
            "content": json.dumps(
                {
                    "overall_ocr_res": {
                        "rec_texts": ["学校实验室工作票", "615实验室", "", "做实验"],
                        "rec_boxes": [[1, 2, 3, 4]],
                    },
                    "model_settings": {"debug": True},
                },
                ensure_ascii=False,
            ),
        }
    ]

    result = _extract_rec_texts_files(json_files)

    assert result[0]["lines"] == ["学校实验室工作票", "615实验室", "做实验"]
    assert result[0]["content"] == "学校实验室工作票\n615实验室\n做实验"
    assert "rec_boxes" not in result[0]["content"]
