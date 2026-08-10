from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

from lxml import etree


REFERENCE = Path(r"C:\Users\xueyuan\Desktop\研究生\文献\工作票识别\电气第二种工作票_可编辑版.docx")
FINAL = Path(r"D:\work\workTicket3\output\WP-001_电气第二种工作票_仿真测试.docx")
EXPECTED_SHA256 = "44b38e7be2723dd156ca44218794c7744967d0fcfc5ef568133bfa3270285e7a"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_nodes(element):
    return element.xpath(".//w:t", namespaces=NS)


def set_text_node(node, value: str) -> None:
    node.text = value
    space_key = f"{{{XML_NS}}}space"
    if value.startswith(" ") or value.endswith(" "):
        node.set(space_key, "preserve")
    else:
        node.attrib.pop(space_key, None)


def replace_text_nodes(element, values: list[str], *, exact: bool = True) -> None:
    nodes = text_nodes(element)
    if exact and len(nodes) != len(values):
        raise ValueError(f"Expected {len(values)} text nodes, found {len(nodes)}")
    if len(nodes) < len(values):
        raise ValueError(f"Insufficient text nodes: need {len(values)}, found {len(nodes)}")
    for index, node in enumerate(nodes):
        set_text_node(node, values[index] if index < len(values) else "")


def replace_cell_text(cell, value: str) -> None:
    paragraphs = cell.xpath("./w:p", namespaces=NS)
    if not paragraphs:
        raise ValueError("Cell has no paragraph")
    nodes = text_nodes(paragraphs[0])
    if not nodes:
        raise ValueError("Cell paragraph has no text node")
    set_text_node(nodes[0], value)
    for node in nodes[1:]:
        set_text_node(node, "")


def build_document_xml(source_xml: bytes) -> bytes:
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(source_xml, parser)
    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        raise ValueError("Document body not found")

    paragraphs = body.xpath("./w:p", namespaces=NS)
    tables = body.xpath("./w:tbl", namespaces=NS)
    if len(paragraphs) != 15 or len(tables) != 3:
        raise ValueError(f"Unexpected template structure: {len(paragraphs)} paragraphs, {len(tables)} tables")

    # P0-P1: 修正模板标题标点，并增加仿真数据标识。
    replace_text_nodes(paragraphs[0], ["电气第二种工作票"])
    replace_text_nodes(
        paragraphs[1],
        ["", "仿真测试数据（项目组构造资料，禁止用于现场作业）"],
    )

    # P2-P8: 工作票核心字段。
    replace_text_nodes(paragraphs[2], ["NO.编号：WP-001"])
    replace_text_nodes(
        paragraphs[3],
        [
            "1.工作负责人：",
            "赵明（虚拟）  ",
            "工作监护人（工作协调人）：",
            "周安（虚拟）",
            " 班组：",
            "项目仿真作业一班",
            " 附页：",
            "0",
            "张",
        ],
    )
    replace_text_nodes(
        paragraphs[4],
        ["2.工作班成员：", "孙宇（虚拟）、韩宁（虚拟）", " 共2人"],
    )
    replace_text_nodes(
        paragraphs[5],
        ["3.工作地点及主要设备名称：", "SIM-A站主变作业区1号主变压器端子箱"],
    )
    replace_text_nodes(
        paragraphs[6],
        ["4.工作内容：", "1号主变压器端子箱外观及温湿度传感器状态核查"],
    )
    replace_text_nodes(
        paragraphs[7],
        [
            "5.计划工作时间：自",
            "2026年8月18日09时00分",
            "至",
            "2026年8月18日10时00分",
        ],
    )
    replace_text_nodes(
        paragraphs[8],
        [
            "6.工作条件（停电或不停电，或邻近及保留带电设备名称）：",
            "不停电；1号主变压器本体及高压侧引线保持带电",
        ],
    )
    replace_text_nodes(paragraphs[9], ["7.配合工作：无。"])
    replace_text_nodes(paragraphs[10], ["8.安全措施及注意事项："])

    # T0: 修正表头用语，其他配合工作记录保持模板空白结构。
    cooperation_rows = tables[0].xpath("./w:tr", namespaces=NS)
    cooperation_header_cells = cooperation_rows[0].xpath("./w:tc", namespaces=NS)
    replace_cell_text(cooperation_header_cells[0], "配合工作项目")

    # T1: 安全措施表。
    safety_rows = tables[1].xpath("./w:tr", namespaces=NS)
    if len(safety_rows) != 12:
        raise ValueError(f"Unexpected safety-table row count: {len(safety_rows)}")

    safety_values = {
        1: (
            "1、作业前核对SIM-A站主变作业区及1号主变压器端子箱名称。",
            "1、（ ）核对作业地点及设备名称无误。",
        ),
        2: (
            "2、在作业区域设置围栏和“止步，高压危险”标示牌。",
            "2、（ ）围栏及标示牌已设置。（编号：SIM-SP-01）",
        ),
        3: (
            "3、工作人员与带电部位保持规定安全距离，不得跨越围栏。",
            "3、（ ）已交代带电部位及安全距离。",
        ),
        4: (
            "4、作业人员应正确佩戴安全帽、穿反光背心，使用绝缘工具。",
            "4、（ ）劳动防护用品及绝缘工具检查合格。",
        ),
    }
    for row_index, pair in safety_values.items():
        cells = safety_rows[row_index].xpath("./w:tc", namespaces=NS)
        if len(cells) != 2:
            raise ValueError(f"Unexpected cell count in safety row {row_index}: {len(cells)}")
        replace_cell_text(cells[0], pair[0])
        replace_cell_text(cells[1], pair[1])

    signature_cells = safety_rows[11].xpath("./w:tc", namespaces=NS)
    if len(signature_cells) != 1:
        raise ValueError(f"Unexpected signature row cell count: {len(signature_cells)}")
    replace_text_nodes(
        signature_cells[0],
        [
            "工作票签发人：模拟签名-林峰  2026年8月17日16时00分",
            "点检签发人：模拟签名-许静  2026年8月17日16时10分",
            "工作票接收人：模拟签名-陈凯  2026年8月18日08时40分",
        ],
    )

    # P11-P14: 许可、试运和负责人变更。
    replace_text_nodes(
        paragraphs[11],
        ["9.许可开工时间：2026年8月18日09时00分  工作许可人：陈凯（虚拟）  工作负责人：赵明（虚拟）"],
    )
    replace_text_nodes(paragraphs[12], ["10.检修设备试运：本次作业不涉及设备试运。"])
    replace_text_nodes(paragraphs[13], ["未试运原因：仅进行外观检查及状态核查，无需试运。"])
    replace_text_nodes(paragraphs[14], ["11.工作负责人变更：无。"])

    # T2: 统一“安全措施”用语，保留空白试运记录。
    trial_rows = tables[2].xpath("./w:tr", namespaces=NS)
    trial_header_cells = trial_rows[0].xpath("./w:tc", namespaces=NS)
    if len(trial_header_cells) != 2:
        raise ValueError(f"Unexpected trial header cell count: {len(trial_header_cells)}")
    replace_cell_text(
        trial_header_cells[0],
        "检修设备试运前，工作票交回，所列安全措施已撤除，可以试运。",
    )
    replace_cell_text(
        trial_header_cells[1],
        "检修设备试运后，工作票所列安全措施已全部执行，可以重新工作。",
    )

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def main() -> None:
    if sha256(REFERENCE) != EXPECTED_SHA256:
        raise RuntimeError("Reference template hash mismatch; fresh distillation required")

    FINAL.parent.mkdir(parents=True, exist_ok=True)
    working = FINAL.with_suffix(".working.docx")
    shutil.copy2(REFERENCE, working)

    with zipfile.ZipFile(working, "r") as source:
        document_xml = source.read("word/document.xml")
        patched_xml = build_document_xml(document_xml)
        with zipfile.ZipFile(FINAL, "w") as target:
            for info in source.infolist():
                data = patched_xml if info.filename == "word/document.xml" else source.read(info.filename)
                target.writestr(info, data)

    working.unlink()
    print(FINAL)
    print(sha256(FINAL))


if __name__ == "__main__":
    main()
